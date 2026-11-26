# bot_whatsapp.py
# Bot do Desconfia.AI no WhatsApp. Funciona por dois caminhos:
#   /webhook  WhatsApp Cloud API da Meta (exige empresa verificada para entregar)
#   /twilio   Sandbox de WhatsApp do Twilio (para testes e para o vídeo)
#   /telegram Bot do Telegram (funciona sem verificação de empresa)
#   /d360/... Sandbox de WhatsApp da 360dialog (número brasileiro, sem conta, 25 mensagens)
#
# A pessoa encaminha a mensagem suspeita para o número do Desconfia.AI e recebe
# a análise ali mesmo. Usa a mesma análise do app (analise.py).
#
# Roda no Render com:  gunicorn bot_whatsapp:app --workers 1 --threads 4 --timeout 60
#
# Variáveis de ambiente (ficam no painel do Render, nunca no GitHub):
#   OPENAI_API_KEY          chave da OpenAI
#   WHATSAPP_TOKEN          token de acesso da Meta
#   WHATSAPP_PHONE_ID       identificação do número de telefone (painel da Meta)
#   WHATSAPP_VERIFY_TOKEN   uma senha que nós inventamos, igual à cadastrada na Meta
#   META_APP_SECRET         chave secreta do app (Configurações do app > Básico)
#   TWILIO_ACCOUNT_SID      Account SID do Twilio (página inicial do Console)
#   TWILIO_AUTH_TOKEN       Auth Token do Twilio (página inicial do Console)
#   TWILIO_WHATSAPP_FROM    número do sandbox, ex.: whatsapp:+14155238886
#   TELEGRAM_TOKEN          token do bot, dado pelo @BotFather
#   TELEGRAM_SECRET         uma senha que nós inventamos: o Telegram a envia em cada aviso
#   TELEGRAM_WEBHOOK_URL    opcional; padrão https://desconfia-ai.onrender.com/telegram
#   D360_API_KEY            chave do sandbox da 360dialog (chega no WhatsApp ao mandar START)
#   D360_SECRET             uma senha que nós inventamos: vai no endereço do webhook

import base64
import hashlib
import html
import hmac
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import date

from flask import Flask, request

from analise import analisar, desarmar_links, juntar_sinais
from ja_paguei import parece_ja_paguei, resposta_whatsapp
from verificacoes import texto_dos_dias

VERSAO_API = "v25.0"
MAX_CARACTERES = 3000     # mensagens maiores são cortadas, para proteger os créditos
MAX_POR_PESSOA = 20       # análises por número por dia
MAX_POR_DIA = 400         # análises somando todo mundo, por dia

app = Flask(__name__)

_ja_vistas = OrderedDict()            # a Meta às vezes manda a mesma mensagem duas vezes
_uso = {"dia": None, "total": 0, "por_pessoa": {}}
_trava = threading.Lock()

FAIXAS = {
    "alto": ("🔴 *Risco alto*", "Há sinais fortes de golpe. Não pague e não clique em links."),
    "medio": ("🟡 *Risco médio*", "Há sinais que pedem cuidado. Confirme pelo canal oficial antes de agir."),
    "baixo": ("🔵 *Risco baixo*", "Não encontramos sinais de golpe nesta mensagem. Isso não garante que ela "
                                 "seja verdadeira: confirme pelo canal oficial antes de pagar qualquer coisa."),
}

BOAS_VINDAS = (
    "Olá! Eu sou o *Desconfia.AI*, a IA que desconfia por você. 🛡️\n\n"
    "Recebeu uma mensagem estranha pedindo dinheiro, Pix ou dados? *Encaminhe a mensagem para mim* "
    "(ou copie e cole aqui). Também pode me contar o que aconteceu, por exemplo uma ligação.\n\n"
    "Eu mostro os sinais de golpe e o que fazer. Não dou veredito: na dúvida, confirme sempre "
    "pelo canal oficial.\n\n"
    "Se você *já pagou*, mande \"já paguei\" que eu mostro como pedir o dinheiro de volta.\n\n"
    "_Não mande senhas nem documentos._"
)

SO_TEXTO = (
    "Por enquanto eu só consigo ler mensagens de texto. Encaminhe a mensagem em texto, "
    "ou copie e cole aqui o que ela diz."
)


# ---------- Segurança ----------

def assinatura_valida(corpo, assinatura):
    """Confere se o aviso veio mesmo da Meta (assinatura com a chave secreta do app)."""
    segredo = os.getenv("META_APP_SECRET", "")
    if not segredo or not assinatura or not assinatura.startswith("sha256="):
        return False
    esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura.split("=", 1)[1])


def pode_analisar(numero):
    with _trava:
        hoje = date.today().isoformat()
        if _uso["dia"] != hoje:
            _uso.update(dia=hoje, total=0, por_pessoa={})
        if _uso["total"] >= MAX_POR_DIA or _uso["por_pessoa"].get(numero, 0) >= MAX_POR_PESSOA:
            return False
        _uso["total"] += 1
        _uso["por_pessoa"][numero] = _uso["por_pessoa"].get(numero, 0) + 1
        return True


def primeira_vez(id_mensagem):
    with _trava:
        if id_mensagem in _ja_vistas:
            return False
        _ja_vistas[id_mensagem] = True
        while len(_ja_vistas) > 1000:
            _ja_vistas.popitem(last=False)
        return True


# ---------- Resposta ----------

def montar_resposta(ficha):
    """Monta a resposta do WhatsApp. Tudo o que vem da mensagem passa por desarmar_links:
    o WhatsApp transformaria "site-do-golpe.com" em link clicável dentro do nosso próprio alerta."""
    d = desarmar_links
    titulo, frase = FAIXAS[ficha["nivel_de_risco"]]
    partes = [f"{titulo}\n{frase}"]

    if ficha.get("explicacao_simples"):
        partes.append(d(ficha["explicacao_simples"]))

    if ficha.get("modo") == "seguranca":
        partes.append("_Modo de segurança: a análise completa está fora do ar agora, então usei só as "
                      "nossas regras fixas e as consultas oficiais. Tente de novo daqui a pouco._")

    sinais = juntar_sinais(ficha)
    if sinais:
        linhas = ["*Por que desconfiar*"]
        for item in sinais:
            linhas.append(f"• {d(item['sinal'])}")
            if item["trecho"]:
                linhas.append(f'   _Na mensagem: "{d(item["trecho"])}"_')
        partes.append("\n".join(linhas))

    verificacoes = ficha.get("verificacoes") or []
    if verificacoes:
        linhas = ["*O que conferimos em fonte oficial*"]
        for v in verificacoes:
            if v["situacao"] == "registrado" and v["dias"] is not None:
                ano, mes, dia = v["registrado_em"].split("-")
                texto = f"registrado em {dia}/{mes}/{ano}, há {texto_dos_dias(v['dias'])}"
            elif v["situacao"] == "registrado":
                texto = "está registrado, mas o registro não informa a data"
            elif v["situacao"] == "nao_registrado":
                texto = "não está registrado. Ninguém é dono desse endereço"
            else:
                texto = "não conseguimos consultar o registro agora"
            linhas.append(f"• {d(v['site'])}: {texto} (fonte: {v['fonte']})")
        partes.append("\n".join(linhas))

    if ficha.get("o_que_fazer"):
        partes.append(f"*O que fazer agora*\n{d(ficha['o_que_fazer'])}")

    if ficha["nivel_de_risco"] in ("alto", "medio"):
        partes.append("🆘 Já fez o pagamento? Mande *já paguei* que eu mostro como pedir o dinheiro de volta.")

    partes.append("_O Desconfia.AI não dá veredito: mostra sinais de risco. "
                  "Na dúvida, confirme sempre pelo canal oficial._")
    return "\n\n".join(partes)[:4000]


def enviar_texto(numero, texto):
    url = f"https://graph.facebook.com/{VERSAO_API}/{os.getenv('WHATSAPP_PHONE_ID')}/messages"
    corpo = json.dumps({
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto, "preview_url": False},
    }).encode()
    pedido = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(pedido, timeout=15) as resposta:
            print(f"[envio] ok para ...{numero[-4:]}: {resposta.status}", flush=True)
    except urllib.error.HTTPError as erro:
        print(f"[envio] ERRO {erro.code}: {erro.read().decode(errors='replace')[:500]}", flush=True)
    except Exception as erro:
        print(f"[envio] ERRO: {erro}", flush=True)


def responder(numero, texto, enviar=None):
    """Roda em segundo plano, para o WhatsApp receber o 'ok' na hora."""
    enviar = enviar or enviar_texto
    texto = texto.strip()
    if parece_ja_paguei(texto):
        enviar(numero, resposta_whatsapp())
        return
    if len(texto) < 20:
        enviar(numero, BOAS_VINDAS)
        return
    if not pode_analisar(numero):
        enviar(numero, "Você chegou ao limite de análises de hoje. Tente de novo amanhã.")
        return
    inicio = time.time()
    print(f"[análise] começando ({len(texto)} caracteres)", flush=True)
    try:
        ficha = analisar(texto[:MAX_CARACTERES])
        print(f"[análise] pronta em {time.time() - inicio:.1f}s, risco {ficha.get('nivel_de_risco')}", flush=True)
        enviar(numero, montar_resposta(ficha))
    except Exception as erro:
        print(f"[análise] ERRO depois de {time.time() - inicio:.1f}s: {type(erro).__name__}: {erro}", flush=True)
        enviar(numero, "Não consegui analisar agora. Tente de novo em alguns segundos.")


# ---------- Twilio ----------

def assinatura_twilio_valida(url, campos, assinatura):
    """Confere se o aviso veio mesmo do Twilio (assinatura com o Auth Token)."""
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token or not assinatura:
        return False
    texto = url + "".join(k + campos[k] for k in sorted(campos))
    esperado = base64.b64encode(hmac.new(token.encode(), texto.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(esperado, assinatura)


def partes_da_mensagem(texto, limite=1500):
    """O WhatsApp pelo Twilio aceita até 1600 caracteres por mensagem: dividimos por parágrafo."""
    partes, atual = [], ""
    for paragrafo in texto.split("\n\n"):
        candidato = f"{atual}\n\n{paragrafo}" if atual else paragrafo
        if len(candidato) <= limite:
            atual = candidato
        else:
            if atual:
                partes.append(atual)
            atual = paragrafo[:limite]
    if atual:
        partes.append(atual)
    return partes


def enviar_twilio(numero, texto):
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    chave = base64.b64encode(f"{sid}:{os.getenv('TWILIO_AUTH_TOKEN', '')}".encode()).decode()
    for i, parte in enumerate(partes_da_mensagem(texto)):
        if i:
            time.sleep(3)  # o sandbox envia no máximo uma mensagem a cada 3 segundos
        corpo = urllib.parse.urlencode({
            "From": os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
            "To": numero,
            "Body": parte,
        }).encode()
        pedido = urllib.request.Request(url, data=corpo, method="POST", headers={
            "Authorization": f"Basic {chave}",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(pedido, timeout=15) as resposta:
                print(f"[twilio envio] ok para ...{numero[-4:]}: {resposta.status}", flush=True)
        except urllib.error.HTTPError as erro:
            print(f"[twilio envio] ERRO {erro.code}: {erro.read().decode(errors='replace')[:500]}", flush=True)
            return
        except Exception as erro:
            print(f"[twilio envio] ERRO: {erro}", flush=True)
            return


# ---------- Rotas ----------

@app.get("/")
def saude():
    return "Desconfia.AI: bot no ar"


@app.get("/diagnostico/<segredo>")
def diagnostico(segredo):
    """Mostra em que linha cada tarefa do servidor está agora (protegido por senha)."""
    esperado = os.getenv("D360_SECRET", "")
    if not esperado or not hmac.compare_digest(segredo, esperado):
        return "segredo inválido", 403
    nomes = {t.ident: t.name for t in threading.enumerate()}
    partes = []
    for ident, quadro in sys._current_frames().items():
        pilha = "".join(traceback.format_stack(quadro)[-6:])
        partes.append(f"=== {nomes.get(ident, ident)} ===\n{pilha}")
    return "\n".join(partes), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/webhook")
def verificar_webhook():
    """A Meta chama este endereço uma vez, para confirmar que o servidor é nosso."""
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN")):
        return request.args.get("hub.challenge", ""), 200
    return "token inválido", 403


# ---------- Telegram ----------

def _telegram(metodo, dados):
    url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN', '')}/{metodo}"
    pedido = urllib.request.Request(url, data=json.dumps(dados).encode(), method="POST",
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=15) as resposta:
        return json.loads(resposta.read().decode())


def para_html(texto):
    """Troca o *negrito* e o _itálico_ do WhatsApp pelas marcas que o Telegram entende."""
    texto = html.escape(texto, quote=False)
    texto = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", texto)
    return re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", texto)


def enviar_telegram(chat_id, texto):
    try:
        _telegram("sendMessage", {"chat_id": chat_id, "text": para_html(texto), "parse_mode": "HTML",
                                  "disable_web_page_preview": True})
        print(f"[telegram envio] ok para ...{str(chat_id)[-4:]}", flush=True)
    except urllib.error.HTTPError as erro:
        print(f"[telegram envio] ERRO {erro.code}: {erro.read().decode(errors='replace')[:300]}", flush=True)
        try:  # se a formatação der problema, manda sem formatação
            _telegram("sendMessage", {"chat_id": chat_id, "text": texto, "disable_web_page_preview": True})
        except Exception as erro2:
            print(f"[telegram envio] ERRO de novo: {erro2}", flush=True)
    except Exception as erro:
        print(f"[telegram envio] ERRO: {erro}", flush=True)


def responder_telegram(chat_id, texto):
    try:
        _telegram("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass
    responder(chat_id, texto, enviar_telegram)


def configurar_telegram():
    """Avisa o Telegram para onde mandar as mensagens (roda quando o servidor liga)."""
    if not os.getenv("TELEGRAM_TOKEN") or not os.getenv("TELEGRAM_SECRET"):
        return
    try:
        resposta = _telegram("setWebhook", {
            "url": os.getenv("TELEGRAM_WEBHOOK_URL", "https://desconfia-ai.onrender.com/telegram"),
            "secret_token": os.getenv("TELEGRAM_SECRET"),
            "allowed_updates": ["message"],
        })
        print(f"[telegram] webhook configurado: {resposta.get('ok')}", flush=True)
    except Exception as erro:
        print(f"[telegram] ERRO ao configurar o webhook: {erro}", flush=True)


@app.post("/telegram")
def receber_telegram():
    segredo = os.getenv("TELEGRAM_SECRET", "")
    if not segredo or not hmac.compare_digest(
            request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), segredo):
        return "segredo inválido", 403

    dados = request.get_json(silent=True) or {}
    if not primeira_vez(f"tg{dados.get('update_id')}"):
        return "ok", 200
    msg = dados.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if not chat_id:
        return "ok", 200
    texto = msg.get("text") or msg.get("caption") or ""
    print(f"[telegram mensagem] de ...{str(chat_id)[-4:]} encaminhada={'forward_origin' in msg}", flush=True)
    if texto.strip():
        threading.Thread(target=responder_telegram, args=(chat_id, texto), daemon=True).start()
    else:
        threading.Thread(target=enviar_telegram, args=(chat_id, SO_TEXTO), daemon=True).start()
    return "ok", 200


threading.Thread(target=configurar_telegram, daemon=True).start()


# ---------- 360dialog (sandbox) ----------

URL_D360 = "https://waba-sandbox.360dialog.io/v1"


def _d360(caminho, dados):
    pedido = urllib.request.Request(f"{URL_D360}/{caminho}", data=json.dumps(dados).encode(), method="POST",
                                    headers={"Content-Type": "application/json",
                                             "D360-API-KEY": os.getenv("D360_API_KEY", "")})
    with urllib.request.urlopen(pedido, timeout=15) as resposta:
        return resposta.status


def enviar_d360(destino, texto):
    campo = "to" if str(destino).isdigit() else "recipient"   # número ou identificação da 360dialog
    try:
        status = _d360("messages", {"messaging_product": "whatsapp", "recipient_type": "individual",
                                    campo: destino, "type": "text", "text": {"body": texto}})
        print(f"[d360 envio] ok para ...{str(destino)[-4:]}: {status}", flush=True)
    except urllib.error.HTTPError as erro:
        print(f"[d360 envio] ERRO {erro.code}: {erro.read().decode(errors='replace')[:300]}", flush=True)
    except Exception as erro:
        print(f"[d360 envio] ERRO: {erro}", flush=True)


def configurar_d360():
    """Cadastra o nosso endereço no sandbox da 360dialog (roda quando o servidor liga)."""
    if not os.getenv("D360_API_KEY") or not os.getenv("D360_SECRET"):
        return
    url = f"https://desconfia-ai.onrender.com/d360/{os.getenv('D360_SECRET')}"
    try:
        print(f"[d360] webhook configurado: {_d360('configs/webhook', {'url': url})}", flush=True)
    except urllib.error.HTTPError as erro:
        print(f"[d360] ERRO ao configurar o webhook {erro.code}: {erro.read().decode(errors='replace')[:300]}", flush=True)
    except Exception as erro:
        print(f"[d360] ERRO ao configurar o webhook: {erro}", flush=True)


@app.post("/d360/<segredo>")
def receber_d360(segredo):
    esperado = os.getenv("D360_SECRET", "")
    if not esperado or not hmac.compare_digest(segredo, esperado):
        return "segredo inválido", 403
    dados = request.get_json(silent=True) or {}
    for entrada in dados.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            for status in valor.get("statuses", []):
                destino = str(status.get("recipient_id") or status.get("recipient_user_id") or "")
                print(f"[d360 status] ...{destino[-4:]}: {status.get('status')} "
                      f"{json.dumps(status.get('errors', []), ensure_ascii=False)}", flush=True)
            for msg in valor.get("messages", []):
                if not primeira_vez(f"d360{msg.get('id')}"):
                    continue
                remetente = str(msg.get("from") or msg.get("from_user_id") or "")
                if not remetente:
                    continue
                print(f"[d360 mensagem] de ...{remetente[-4:]} tipo {msg.get('type')}", flush=True)
                if msg.get("type") == "text":
                    texto = (msg.get("text") or {}).get("body", "")
                    threading.Thread(target=responder, args=(remetente, texto, enviar_d360), daemon=True).start()
                else:
                    threading.Thread(target=enviar_d360, args=(remetente, SO_TEXTO), daemon=True).start()
    return "ok", 200


threading.Thread(target=configurar_d360, daemon=True).start()


@app.post("/twilio")
def receber_twilio():
    campos = request.form.to_dict()
    url = os.getenv("TWILIO_WEBHOOK_URL") or f"https://{request.host}{request.path}"
    if not assinatura_twilio_valida(url, campos, request.headers.get("X-Twilio-Signature")):
        print("[twilio] assinatura inválida", flush=True)
        return "assinatura inválida", 403

    vazio = ('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', 200,
             {"Content-Type": "text/xml"})
    if not primeira_vez(campos.get("MessageSid")):
        return vazio
    numero = campos.get("From", "")
    print(f"[twilio mensagem] de ...{numero[-4:]} mídias {campos.get('NumMedia', '0')}", flush=True)
    texto = campos.get("Body", "")
    if texto.strip():
        threading.Thread(target=responder, args=(numero, texto, enviar_twilio), daemon=True).start()
    else:
        threading.Thread(target=enviar_twilio, args=(numero, SO_TEXTO), daemon=True).start()
    return vazio


@app.post("/webhook")
def receber():
    corpo = request.get_data()
    if not assinatura_valida(corpo, request.headers.get("X-Hub-Signature-256")):
        return "assinatura inválida", 403

    dados = json.loads(corpo or b"{}")
    for entrada in dados.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})

            # Avisos de entrega: "enviada", "entregue", "lida" ou "falhou" (com o motivo)
            for status in valor.get("statuses", []):
                print(f"[status] ...{status.get('recipient_id', '')[-4:]}: {status.get('status')} "
                      f"{json.dumps(status.get('errors', []), ensure_ascii=False)}", flush=True)

            for msg in valor.get("messages", []):
                if not primeira_vez(msg.get("id")):
                    continue
                numero = msg.get("from")
                print(f"[mensagem] de ...{numero[-4:]} ({len(numero)} dígitos) tipo {msg.get('type')}", flush=True)
                if msg.get("type") == "text":
                    texto = msg.get("text", {}).get("body", "")
                    threading.Thread(target=responder, args=(numero, texto), daemon=True).start()
                else:
                    threading.Thread(target=enviar_texto, args=(numero, SO_TEXTO), daemon=True).start()
    return "ok", 200

# bot_whatsapp.py
# Bot do Desconfia.AI no WhatsApp (WhatsApp Cloud API da Meta).
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

import hashlib
import hmac
import json
import os
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import date

from flask import Flask, request

from analise import analisar, juntar_sinais
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
    "Recebeu uma mensagem estranha pedindo dinheiro, Pix ou dados? *Encaminhe ela para mim* "
    "(ou copie e cole aqui). Também pode me contar o que aconteceu, por exemplo uma ligação.\n\n"
    "Eu mostro os sinais de golpe e o que fazer. Não dou veredito: na dúvida, confirme sempre "
    "pelo canal oficial.\n\n"
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
    titulo, frase = FAIXAS[ficha["nivel_de_risco"]]
    partes = [f"{titulo}\n{frase}"]

    if ficha.get("explicacao_simples"):
        partes.append(ficha["explicacao_simples"])

    sinais = juntar_sinais(ficha)
    if sinais:
        linhas = ["*Por que desconfiar*"]
        for item in sinais:
            linhas.append(f"• {item['sinal']}")
            if item["trecho"]:
                linhas.append(f'   _Na mensagem: "{item["trecho"]}"_')
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
            linhas.append(f"• {v['site']}: {texto} (fonte: {v['fonte']})")
        partes.append("\n".join(linhas))

    if ficha.get("o_que_fazer"):
        partes.append(f"*O que fazer agora*\n{ficha['o_que_fazer']}")

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


def responder(numero, texto):
    """Roda em segundo plano, para a Meta receber o 'ok' na hora."""
    texto = texto.strip()
    if len(texto) < 20:
        enviar_texto(numero, BOAS_VINDAS)
        return
    if not pode_analisar(numero):
        enviar_texto(numero, "Você chegou ao limite de análises de hoje. Tente de novo amanhã.")
        return
    try:
        ficha = analisar(texto[:MAX_CARACTERES])
        enviar_texto(numero, montar_resposta(ficha))
    except Exception as erro:
        print(f"[análise] ERRO: {erro}", flush=True)
        enviar_texto(numero, "Não consegui analisar agora. Tente de novo em alguns segundos.")


# ---------- Rotas ----------

@app.get("/")
def saude():
    return "Desconfia.AI: bot no ar"


@app.get("/webhook")
def verificar_webhook():
    """A Meta chama este endereço uma vez, para confirmar que o servidor é nosso."""
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN")):
        return request.args.get("hub.challenge", ""), 200
    return "token inválido", 403


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

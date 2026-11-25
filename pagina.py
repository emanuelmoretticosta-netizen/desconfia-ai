# pagina.py
# Abre a página do link da mensagem pela Firecrawl, nos servidores dela: nem a pessoa nem o
# nosso servidor acessam o site suspeito. Depois, regras fixas conferem o que a página pede
# (senha, cartão, código, CPF, Pix, instalar aplicativo) e se ela finge ser uma marca conhecida.
#
# O texto da página é só um dado: ele NÃO vai para a IA, então uma página de golpe não
# consegue dar ordens a ela. Se a Firecrawl falhar, o laudo sai normalmente, sem esta parte.
#
# A chave fica no .env (FIRECRAWL_API_KEY) ou nos Secrets do Streamlit, nunca no código.

import json
import os
import re
import time
import urllib.error
import urllib.request

from marcas import MARCAS
from verificacoes import dominio_registravel

ENDERECO_FIRECRAWL = "https://api.firecrawl.dev/v2/scrape"
TEMPO_LIMITE = 12            # segundos de espera pela Firecrawl (o laudo não fica preso)
GUARDAR_POR = 6 * 3600       # a mesma página não é aberta de novo por 6 horas (economiza créditos)
MAX_TEXTO = 30000            # quantos caracteres da página são conferidos pelas regras

ENCURTADORES = {"bit.ly", "tinyurl.com", "cutt.ly", "encurtador.com.br", "is.gd", "t.co", "rebrand.ly",
                "shre.ink", "abre.ai"}

# O que a página pede: (nome mostrado no laudo, padrão, é grave?)
# Os graves exigem um PEDIDO de verdade ("digite sua senha"), e não uma simples menção
# ("Esqueci minha senha" no rodapé de qualquer site). Só os graves aumentam o risco:
# CPF, Pix e boleto aparecem em muitos sites legítimos, então só são listados no laudo.
PEDIDOS = [
    ("senha", r"(digite|informe|insira|confirme|coloque|cadastre)\s+(a\s+|sua\s+|seu\s+cpf\s+e\s+(a\s+|sua\s+)?)?senha|"
              r"cpf e (sua )?senha|conta e senha|senha (do cart[aã]o|de [46] d[ií]gitos|eletr[oô]nica)|^\s*senha\s*:?\s*$", True),
    ("dados do cartão", r"n[uú]mero do cart[aã]o|\bcvv\b|c[oó]digo de seguran[cç]a do cart[aã]o|validade do cart[aã]o", True),
    ("código de verificação", r"(digite|informe|insira) o c[oó]digo|c[oó]digo (de verifica[cç][aã]o|recebido por sms|"
                              r"enviado por sms)", True),
    ("instalar um aplicativo", r"\.apk\b|baixe o aplicativo|instale o aplicativo|baixar o aplicativo", True),
    ("CPF", r"(digite|informe|insira) (o |seu )?cpf|^\s*cpf\s*:?\s*$", False),
    ("nome da mãe ou data de nascimento", r"nome da m[aã]e|data de nascimento", False),
    ("pagamento por Pix ou boleto", r"chave pix|pix copia e cola|\bpague (o boleto|via pix|agora)|efetuar pagamento", False),
]

_guardadas = {}  # endereço -> (momento, resultado)


def _texto(valor):
    """A Firecrawl às vezes devolve listas (ex.: título repetido na página): fica só o primeiro, como texto."""
    if isinstance(valor, list):
        valor = valor[0] if valor else None
    return None if valor is None else str(valor)


def _oficiais():
    return {o for _, (_, lista) in MARCAS.items() for o in lista}


def escolher_link(mensagem, sites):
    """Escolhe o primeiro link suspeito da mensagem (nunca sites oficiais) e monta o endereço completo."""
    oficiais = _oficiais()
    for site in sorted(sites):
        dominio = dominio_registravel(site) or site
        if dominio in oficiais or dominio == "gov.br" or dominio.endswith(".gov.br"):
            continue
        achado = re.search(r"(?:https?://)?(?:www\.)?" + re.escape(site) + r"[^\s<>\"')\]]*", mensagem, re.IGNORECASE)
        endereco = achado.group(0) if achado else site
        endereco = endereco.rstrip(".,;:!?")
        if not endereco.lower().startswith(("http://", "https://")):
            endereco = "https://" + endereco
        return endereco
    return None


def abrir_pagina(endereco):
    """Pede à Firecrawl o texto e uma captura da página. Devolve um dicionário, ou None sem chave."""
    chave = os.getenv("FIRECRAWL_API_KEY")
    if not chave or not endereco:
        return None
    guardada = _guardadas.get(endereco)
    if guardada and time.time() - guardada[0] < GUARDAR_POR:
        return guardada[1]

    corpo = json.dumps({"url": endereco, "formats": ["markdown", "screenshot"],
                        "timeout": (TEMPO_LIMITE - 3) * 1000}).encode("utf-8")
    pedido = urllib.request.Request(ENDERECO_FIRECRAWL, data=corpo, method="POST", headers={
        "Authorization": f"Bearer {chave}", "Content-Type": "application/json"})
    resultado = {"endereco": endereco, "ok": False, "titulo": None, "destino": None, "status": None,
                 "captura": None, "texto": ""}
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        info = (dados or {}).get("data") or {}
        meta = info.get("metadata") or {}
        try:
            status = int(_texto(meta.get("statusCode")) or 200)
        except ValueError:
            status = None
        resultado.update({
            "ok": bool(dados.get("success")) and status is not None and 200 <= status < 400,
            "titulo": _texto(meta.get("title")),
            "destino": _texto(meta.get("url") or meta.get("sourceURL")),
            "status": status,
            "captura": _texto(info.get("screenshot")),
            "texto": (_texto(info.get("markdown")) or "")[:MAX_TEXTO],
        })
    except urllib.error.HTTPError as erro:
        resultado["status"] = erro.code
        print(f"[firecrawl] erro {erro.code}", flush=True)
    except Exception as erro:  # demora, sem internet, resposta estranha: o laudo segue sem esta parte
        print(f"[firecrawl] não abriu a página: {type(erro).__name__}", flush=True)
    _guardadas[endereco] = (time.time(), resultado)
    return resultado


def ler_pagina(resultado):
    """Confere, com regras fixas, o que a página pede e se ela finge ser uma marca conhecida."""
    texto = f"{resultado.get('titulo') or ''}\n{resultado.get('texto') or ''}".lower()
    pede = [nome for nome, padrao, _ in PEDIDOS if re.search(padrao, texto, re.MULTILINE)]
    graves = [nome for nome, padrao, grave in PEDIDOS if grave and re.search(padrao, texto, re.MULTILINE)]

    # A marca é procurada só no TÍTULO da página: uma página legítima pode citar marcas no texto
    # (uma lista de lojas, por exemplo) sem fingir ser nenhuma delas.
    marca, oficial = None, None
    inicio = (resultado.get("titulo") or "").lower()
    dominio = dominio_registravel(re.sub(r"^https?://", "", resultado.get("destino") or resultado.get("endereco") or "")
                                  .split("/")[0]) or ""
    for nome_marca, (_, sites_oficiais) in MARCAS.items():
        if nome_marca == "Caixa" and not re.search(r"caixa (econ[oô]mica|tem)", inicio):
            continue
        if re.search(r"\b" + re.escape(nome_marca.lower()) + r"\b", inicio) and dominio not in sites_oficiais:
            marca, oficial = nome_marca, sites_oficiais[0]
            break
    return {"pede": pede, "graves": graves, "marca": marca, "oficial": oficial}


def juntar_lista(itens):
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def sinais_da_pagina(resultado):
    """Transforma o que a página pede em sinais de risco (só aumentam o risco, nunca diminuem)."""
    if not resultado or not resultado.get("ok"):
        return []
    leitura = ler_pagina(resultado)
    sinais = []
    if leitura["graves"]:
        sinais.append({"categoria": "pagina", "risco": "alto",
                       "sinal": f"A página do link pede {juntar_lista(leitura['graves'])}. Banco, loja ou órgão "
                                "público não pede isso por um link recebido em mensagem."})
    if leitura["marca"]:
        sinais.append({"categoria": "imitacao", "risco": "alto",
                       "sinal": f"A página se apresenta como \"{leitura['marca']}\", mas o endereço não é o site "
                                f"oficial ({leitura['oficial']})."})
    return sinais


def resumo_para_o_laudo(resultado):
    """O que o app mostra sobre a página (sem o texto inteiro dela)."""
    if not resultado:
        return None
    leitura = ler_pagina(resultado) if resultado.get("ok") else {"pede": [], "marca": None}
    return {"endereco": resultado.get("endereco"), "ok": resultado.get("ok"), "titulo": resultado.get("titulo"),
            "destino": resultado.get("destino"), "captura": resultado.get("captura"),
            "pede": leitura["pede"], "marca": leitura.get("marca")}

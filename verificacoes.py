# verificacoes.py
# Consultas a fontes públicas que não dependem da opinião da IA.
#
# Idade do site: perguntamos ao registro oficial de domínios (protocolo RDAP)
# quando o endereço foi registrado. Para sites .br, a fonte é o Registro.br.
# Para os outros (.com, .net...), o rdap.org indica o registro oficial certo.
#
# Para testar sozinho (não gasta crédito da OpenAI):  python verificacoes.py

import json
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

TEMPO_LIMITE = 6          # segundos de espera por consulta
MAX_SITES = 3             # quantos sites de uma mensagem consultamos
DIAS_MUITO_NOVO = 30      # registrado há até 30 dias: risco alto
DIAS_NOVO = 90            # registrado há até 90 dias: risco médio

# Categorias do .br em que o nome fica no 3º nível (ex.: loja.com.br)
CATEGORIAS_BR = {
    "com", "net", "org", "gov", "edu", "art", "blog", "eco", "emp", "ind", "inf",
    "log", "med", "nom", "seg", "tec", "tur", "app", "dev", "srv", "adv", "eng",
    "arq", "mil", "jus", "leg", "mp", "def", "coop", "rec", "radio", "tv", "ong",
}

_guardados = {}  # respostas já consultadas, para não perguntar duas vezes


def dominio_registravel(site):
    """'app.loja.com.br' vira 'loja.com.br'; 'www.exemplo.com' vira 'exemplo.com'."""
    partes = [p for p in site.lower().strip(".").split(".") if p]
    if len(partes) < 2:
        return None
    if partes[-1] == "br" and len(partes) >= 3 and partes[-2] in CATEGORIAS_BR:
        return ".".join(partes[-3:])
    if len(partes[-1]) == 2 and len(partes) >= 3 and partes[-2] in {"com", "net", "org", "gov", "edu", "co"}:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def _endereco_da_consulta(dominio):
    if dominio.endswith(".br"):
        return "https://rdap.registro.br/domain/" + dominio, "Registro.br"
    return "https://rdap.org/domain/" + dominio, "registro oficial do domínio (RDAP)"


def data_de_registro(dados):
    """Procura no RDAP a data em que o domínio foi registrado."""
    for evento in dados.get("events") or []:
        if evento.get("eventAction") == "registration" and evento.get("eventDate"):
            try:
                return datetime.fromisoformat(evento["eventDate"].replace("Z", "+00:00")).date()
            except ValueError:
                return None
    return None


def consultar_dominio(site, hoje=None):
    """Devolve o que o registro oficial diz sobre o site.

    situacao: "registrado", "nao_registrado" ou "sem_resposta".
    """
    dominio = dominio_registravel(site)
    if not dominio:
        return None
    if dominio in _guardados:
        return _guardados[dominio]

    url, nome_fonte = _endereco_da_consulta(dominio)
    resultado = {"site": dominio, "fonte": nome_fonte, "link": url,
                 "situacao": "sem_resposta", "registrado_em": None, "dias": None}
    pedido = urllib.request.Request(url, headers={
        "Accept": "application/rdap+json, application/json",
        "User-Agent": "Desconfia.AI (projeto Hack Brasil 2026)",
    })
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        criado = data_de_registro(dados)
        resultado["situacao"] = "registrado"
        if criado:
            resultado["registrado_em"] = criado.isoformat()
            resultado["dias"] = ((hoje or date.today()) - criado).days
    except urllib.error.HTTPError as erro:
        # 404 do registro oficial = ninguém registrou esse endereço.
        # 404 do próprio rdap.org = ele não conhece o registro desse tipo de site.
        veio_do_registro = urllib.parse.urlparse(erro.geturl() or url).hostname != "rdap.org"
        if erro.code == 404 and veio_do_registro:
            resultado["situacao"] = "nao_registrado"
    except Exception:
        pass  # sem internet, demora demais ou resposta estranha: não afirmamos nada

    if resultado["situacao"] != "sem_resposta":
        _guardados[dominio] = resultado
    return resultado


def consultar_sites(sites, ignorar=()):
    """Consulta até MAX_SITES sites ao mesmo tempo."""
    escolhidos = []
    for site in sites:
        dominio = dominio_registravel(site)
        if dominio and dominio not in escolhidos and dominio not in ignorar:
            escolhidos.append(dominio)
    escolhidos = escolhidos[:MAX_SITES]
    if not escolhidos:
        return []
    with ThreadPoolExecutor(max_workers=len(escolhidos)) as grupo:
        return [r for r in grupo.map(consultar_dominio, escolhidos) if r]


def sinais_dos_sites(verificacoes):
    """Transforma as consultas em sinais de risco (só aumentam o risco, nunca diminuem)."""
    sinais = []
    for v in verificacoes:
        if v["situacao"] == "nao_registrado":
            sinais.append({
                "categoria": "dominio",
                "sinal": f"O site {v['site']} não está registrado: ninguém é dono desse endereço. "
                         "Mandar para um site que não existe é comum em mensagens falsas.",
                "risco": "medio",
            })
        elif v["dias"] is not None and v["dias"] <= DIAS_NOVO:
            sinais.append({
                "categoria": "dominio",
                "sinal": f"O site {v['site']} foi criado há só {texto_dos_dias(v['dias'])}. "
                         "Sites de golpe costumam ser novos, criados para durar poucos dias.",
                "risco": "alto" if v["dias"] <= DIAS_MUITO_NOVO else "medio",
            })
    return sinais


def texto_dos_dias(dias):
    if dias <= 0:
        return "menos de um dia"
    if dias == 1:
        return "1 dia"
    if dias < 60:
        return f"{dias} dias"
    if dias < 730:
        return f"{dias // 30} meses"
    return f"{dias // 365} anos"


if __name__ == "__main__":
    for site in ["registro.br", "google.com", "www.bcb.gov.br", "valores-receber-brasil.com",
                 "este-site-nao-existe-desconfia-teste-123.com.br"]:
        v = consultar_dominio(site)
        if v["situacao"] == "registrado":
            idade = texto_dos_dias(v["dias"]) if v["dias"] is not None else "data não informada"
            print(f"{v['site']:50} registrado em {v['registrado_em']} (há {idade})  fonte: {v['fonte']}")
        elif v["situacao"] == "nao_registrado":
            print(f"{v['site']:50} NÃO está registrado  fonte: {v['fonte']}")
        else:
            print(f"{v['site']:50} sem resposta (sem internet ou o registro demorou)")

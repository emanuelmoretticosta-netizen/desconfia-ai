# marcas.py
# Detecta sites que imitam marcas conhecidas (typosquatting).
#
# Golpistas registram endereços parecidos com os de empresas famosas, como "nubanck-seguranca.com"
# ou "bradescco-atualizacao.com". Aqui comparamos cada site da mensagem com os sites oficiais
# das marcas mais imitadas em golpes no Brasil. Não depende da IA: é uma comparação fixa.

from difflib import SequenceMatcher

from verificacoes import dominio_registravel

# marca: (nomes que aparecem nos endereços, sites oficiais)
MARCAS = {
    "Nubank": (["nubank"], ["nubank.com.br"]),
    "Banco do Brasil": (["bancodobrasil"], ["bb.com.br"]),
    "Caixa": (["caixa", "caixatem"], ["caixa.gov.br"]),
    "Itaú": (["itau"], ["itau.com.br"]),
    "Bradesco": (["bradesco"], ["bradesco.com.br"]),
    "Santander": (["santander"], ["santander.com.br"]),
    "Banco Inter": (["bancointer"], ["inter.co", "bancointer.com.br"]),
    "C6 Bank": (["c6bank"], ["c6bank.com.br"]),
    "PicPay": (["picpay"], ["picpay.com"]),
    "Mercado Pago": (["mercadopago"], ["mercadopago.com.br"]),
    "PagBank": (["pagbank", "pagseguro"], ["pagbank.com.br", "pagseguro.uol.com.br"]),
    "Sicredi": (["sicredi"], ["sicredi.com.br"]),
    "Sicoob": (["sicoob"], ["sicoob.com.br"]),
    "Mercado Livre": (["mercadolivre"], ["mercadolivre.com.br"]),
    "Magazine Luiza": (["magazineluiza", "magalu"], ["magazineluiza.com.br", "magalu.com"]),
    "Americanas": (["americanas"], ["americanas.com.br"]),
    "Casas Bahia": (["casasbahia"], ["casasbahia.com.br"]),
    "Amazon": (["amazon"], ["amazon.com.br", "amazon.com"]),
    "Shopee": (["shopee"], ["shopee.com.br"]),
    "Correios": (["correios"], ["correios.com.br"]),
    "Serasa": (["serasa"], ["serasa.com.br"]),
    "iFood": (["ifood"], ["ifood.com.br"]),
    "Netflix": (["netflix"], ["netflix.com"]),
}

# "caixa" sozinho é uma palavra comum (caixa de som, caixa d'água): só conta junto de termos bancários
CONTEXTO_CAIXA = {"tem", "conta", "fgts", "saque", "desbloqueio", "beneficio", "auxilio", "pis", "economica"}


def _partes(dominio):
    """'nubanck-atualizacao.com' vira ['nubanck', 'atualizacao']."""
    nome = dominio.split(".")[0]
    return [p for p in nome.lower().split("-") if p]


def _parecido(parte, nome):
    """Mesmo nome com um erro de digitação (letra trocada, a mais ou a menos)."""
    if parte == nome or len(nome) < 5 or abs(len(parte) - len(nome)) > 1 or parte[0] != nome[0]:
        return False
    return SequenceMatcher(None, parte, nome).ratio() >= 0.8


def imitacoes(sites):
    """Devolve uma lista de {site, marca, oficial, tipo} para os sites que imitam uma marca."""
    achados = []
    for site in sites:
        dominio = dominio_registravel(site)
        if not dominio or dominio == "gov.br" or dominio.endswith(".gov.br"):
            continue
        partes = _partes(dominio)
        for marca, (nomes, oficiais) in MARCAS.items():
            if dominio in oficiais:
                break  # é o site oficial dessa marca
            tipo = None
            for parte in partes:
                for nome in nomes:
                    if parte == nome:
                        if nome == "caixa" and not CONTEXTO_CAIXA.intersection(partes):
                            continue
                        tipo = "nome"
                    elif _parecido(parte, nome):
                        tipo = "erro"
            if tipo:
                achados.append({"site": dominio, "marca": marca, "oficial": oficiais[0], "tipo": tipo})
                break
    return achados


def frase(achado):
    if achado["tipo"] == "erro":
        return (f"O site {achado['site']} imita o nome \"{achado['marca']}\" com um erro de digitação, "
                f"truque comum em golpes. O site oficial é {achado['oficial']}.")
    return (f"O site {achado['site']} usa o nome \"{achado['marca']}\", mas não é o site oficial "
            f"({achado['oficial']}).")


if __name__ == "__main__":
    for s in ["nubanck-atualizacao-seguranca.com", "caixa-tem-desbloqueio-conta.com", "banco-bradescco-seguranca.com",
              "magazineluiza-queima-estoque.com", "acordo-divida-seraza.com", "app.nubank.com.br", "caixadesom.com.br",
              "loja-caixa-de-som.com", "turismo-amazonas.com.br", "valoresareceber.bcb.gov.br", "itau-pontos-resgate.com"]:
        print(f"{s:40}", [frase(a) for a in imitacoes([s])])

# manter_acordado.py
# Abre o app como uma pessoa faria, para o Streamlit Community Cloud não colocá-lo para dormir.
# Se o app estiver dormindo, clica no botão para acordá-lo. Roda sozinho pelo GitHub Actions
# (arquivo .github/workflows/manter-acordado.yml), a cada 4 horas.

import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

APP = "https://desconfia-ai.streamlit.app"
BOT = "https://desconfia-ai.onrender.com/"


def app_esta_no_ar(pagina):
    return any("Desconfia.AI" in quadro.content() for quadro in pagina.frames)


def main():
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(APP, wait_until="domcontentloaded", timeout=120_000)
        pagina.wait_for_timeout(10_000)
        botao = pagina.get_by_role("button", name=re.compile("get this app back up", re.IGNORECASE))
        if botao.count():
            print("O app estava dormindo: acordando...")
            botao.first.click()
            pagina.wait_for_timeout(90_000)
        for _ in range(6):  # espera o app carregar (até 1 minuto)
            if app_esta_no_ar(pagina):
                break
            pagina.wait_for_timeout(10_000)
        no_ar = app_esta_no_ar(pagina)
        navegador.close()

    try:  # acorda também o servidor do bot do WhatsApp
        with urllib.request.urlopen(BOT, timeout=90) as resposta:
            print(f"Bot do WhatsApp respondeu: {resposta.status}")
    except Exception as erro:
        print(f"Bot do WhatsApp não respondeu: {erro}")

    if not no_ar:
        print("ATENÇÃO: o app não carregou.")
        sys.exit(1)  # o GitHub avisa por e-mail quando isso falha
    print("App no ar.")


if __name__ == "__main__":
    main()

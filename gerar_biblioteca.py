# gerar_biblioteca.py
# Gera dados/biblioteca_golpes.csv a partir da biblioteca de golpes da Maria Clara
# (planilha "Tipos de Golpes.xlsx"). O app usa esse arquivo para mostrar, no laudo,
# a orientação oficial de cada tipo de golpe, com a fonte.
#
# Rodar de novo sempre que a planilha mudar:  python gerar_biblioteca.py
# O openpyxl só é preciso aqui (pip install openpyxl): o app lê o CSV, sem ele.

import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from openpyxl import load_workbook

PASTA = Path(__file__).parent
SAIDA = PASTA / "dados" / "biblioteca_golpes.csv"
COLUNAS = {"id": "id", "tipo de golpe": "tipo", "descrição": "descricao", "sinais de alerta": "sinais",
           "como proceder": "como_proceder", "fonte": "fonte", "link": "link"}


def limpar(texto):
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def limpar_link(link):
    """Tira parâmetros de rastreamento (como ?utm_source=...) e aceita só endereços https."""
    partes = urlsplit(limpar(link))
    if partes.scheme != "https":
        return ""
    return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))


def achar_planilha():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    exata = PASTA / "Tipos de Golpes.xlsx"
    if exata.exists():
        return exata
    outras = sorted(PASTA.glob("Tipos de Golpes*.xlsx"))
    if not outras:
        sys.exit("Planilha 'Tipos de Golpes.xlsx' não encontrada na pasta do projeto.")
    return outras[0]


def main():
    planilha = achar_planilha()
    livro = load_workbook(planilha, data_only=True)
    aba = next(a for a in livro.worksheets if a.title.lower().startswith("golpes"))
    linhas = list(aba.iter_rows(values_only=True))
    cabecalho = [limpar(c).lower() for c in linhas[0]]
    posicao = {campo: cabecalho.index(nome) for nome, campo in COLUNAS.items()}

    registros = []
    for linha in linhas[1:]:
        ident = limpar(linha[posicao["id"]])
        if not re.fullmatch(r"G_\d+", ident):
            continue
        registro = {campo: limpar(linha[i]) for campo, i in posicao.items()}
        registro["link"] = limpar_link(registro["link"])
        registros.append(registro)

    SAIDA.parent.mkdir(exist_ok=True)
    with SAIDA.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(COLUNAS.values()))
        escritor.writeheader()
        escritor.writerows(registros)
    print(f"{len(registros)} tipos de golpe salvos em {SAIDA.relative_to(PASTA)} (a partir de {planilha.name})")


if __name__ == "__main__":
    main()

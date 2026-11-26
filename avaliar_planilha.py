# avaliar_planilha.py
# Roda a base de testes da equipe (dados/testes_golpes.csv) e mede quantas o Desconfia.AI acerta.
#
# A planilha tem as colunas: ID, Tipo de golpe, Entrada - texto, Link - página falsa,
# Saída obtida, Resultado. Linhas cujo "Tipo de golpe" começa com "Normal" ou é "Grupo controle"
# são mensagens legítimas: o certo é risco baixo. As demais são golpes: o certo é risco médio ou alto.
#
# Os links usam terminações reservadas (.invalid, .test, .example), que não existem na
# internet, para nunca apontar para o site de alguém.
#
# Como rodar (na pasta do projeto, com a chave da OpenAI no arquivo .env):
#     python avaliar_planilha.py                          base da equipe (dados/testes_golpes.csv)
#     python avaliar_planilha.py dados/testes_novos.csv   teste independente (mensagens novas da Maria Clara)
# O resultado sai na tela e em dados/resultados_<nome da planilha>.csv.

try:
    import truststore  # no Windows, usa os certificados do próprio sistema
    truststore.inject_into_ssl()
except ImportError:
    pass

import csv
import re
import sys
from pathlib import Path

from analise import analisar, juntar_sinais

PASTA = Path(__file__).with_name("dados")
ENTRADA = PASTA / "testes_golpes.csv"
SAIDA = PASTA / "resultados_testes.csv"


TERMINACOES_RESERVADAS = re.compile(r"\.(invalid|test|example)\b", re.IGNORECASE)
PRIMEIRO_LINK = re.compile(r"https?://[^\s\[\]()<>]+")


def eh_mensagem_normal(linha):
    tipo = (linha.get("Tipo de golpe") or "").strip().lower()
    return tipo.startswith("normal") or tipo.startswith("grupo controle")


def montar_mensagem(linha):
    """Junta o texto e o link. Troca a terminação reservada por .com só na hora de analisar:
    com .invalid ou .test a IA percebe que é um teste, e golpe de verdade usa .com ou .com.br.
    Nenhum site é acessado: só o registro público de domínios é consultado."""
    texto = (linha.get("Entrada - texto") or "").strip()
    link = (linha.get("Link - página falsa") or "").strip()
    achado = PRIMEIRO_LINK.search(link)  # a planilha às vezes traz o link em formato [texto](link)
    link = achado.group(0) if achado else link
    mensagem = f"{texto}\n{link}" if link and link not in texto else texto
    return TERMINACOES_RESERVADAS.sub(".com", mensagem)


def rodar(entrada=ENTRADA):
    entrada = Path(entrada)
    saida = SAIDA if entrada == ENTRADA else entrada.with_name(f"resultados_{entrada.name}")
    linhas = list(csv.DictReader(entrada.open(encoding="utf-8-sig")))
    golpes = normais = golpes_ok = normais_ok = 0
    for linha in linhas:
        if not (linha.get("Entrada - texto") or "").strip():
            continue
        normal = eh_mensagem_normal(linha)
        ficha = analisar(montar_mensagem(linha))
        risco = ficha["nivel_de_risco"]
        ok = (risco == "baixo") if normal else (risco in ("medio", "alto"))
        sinais = [item["sinal"] for item in juntar_sinais(ficha)][:2]
        linha["Saída obtida"] = f"risco {risco}" + (": " + " | ".join(sinais) if sinais else "")
        linha["Resultado"] = "OK" if ok else "ERRO"
        if normal:
            normais += 1
            normais_ok += ok
        else:
            golpes += 1
            golpes_ok += ok
        print(f"{linha['Resultado']:4} | {linha.get('ID', ''):6} | {linha.get('Tipo de golpe', '')[:26]:26} | risco {risco}")

    with saida.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas)

    print()
    if golpes:
        print(f"Golpes detectados (risco médio ou alto): {golpes_ok} de {golpes} ({golpes_ok / golpes:.0%})")
    if normais:
        print(f"Mensagens normais sem alarme falso: {normais_ok} de {normais} ({normais_ok / normais:.0%})")
    print(f"Detalhes salvos em {saida}")


if __name__ == "__main__":
    rodar(sys.argv[1] if len(sys.argv) > 1 else ENTRADA)

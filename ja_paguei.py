# ja_paguei.py
# Modo "já paguei": o que fazer quando a pessoa já caiu no golpe.
# Usado pelo app (app.py) e pelo bot do WhatsApp (bot_whatsapp.py).
#
# Regras do MED (Mecanismo Especial de Devolução do Pix), conferidas em novembro de 2026:
# - o pedido de devolução é feito no próprio banco, em até 80 dias depois do Pix;
# - desde 1/10/2025 os bancos oferecem um botão de contestação no app, sem precisar de atendente;
# - o banco analisa em até 7 dias; se confirmar a fraude, devolve em até 96 horas,
#   total ou parcialmente, conforme o dinheiro que ainda estiver nas contas do golpista;
# - desde 2/2/2026 o MED também rastreia as contas para onde o dinheiro foi passado.
# Fontes: Agência Brasil (set/2026) e InfoMoney/O Globo (nov/2025), links em FONTES.

import re
from datetime import date

PASSOS = [
    ("Conteste o Pix no app do seu banco, agora",
     "Abra o extrato, toque no Pix que você fez e procure a opção de contestar ou de devolução por "
     "golpe. Os bancos têm esse botão desde outubro de 2025. Se não achar, ligue para o número que "
     "fica atrás do seu cartão e peça a abertura do MED. O prazo é de até 80 dias, mas quanto antes, "
     "maior a chance: o banco do golpista bloqueia o que ainda estiver na conta."),
    ("Registre um boletim de ocorrência",
     "Pode ser pela delegacia online do seu estado, sem sair de casa. Leve o texto pronto abaixo."),
    ("Guarde as provas",
     "Comprovante do Pix, prints da conversa, o anúncio ou a mensagem, e os dados de quem recebeu o dinheiro."),
    ("Proteja suas contas",
     "Se você passou senha, código ou dados do cartão, troque as senhas e avise o banco na mesma hora."),
    ("Avise outras pessoas",
     "Se o golpista usou o nome de um parente ou o seu WhatsApp, avise a família e os contatos para "
     "ninguém mais cair."),
]

DEPOIS = [
    "O banco analisa o caso em até 7 dias.",
    "Se confirmar a fraude, devolve em até 96 horas, total ou em parte, conforme o dinheiro que "
    "ainda estiver nas contas do golpista.",
    "O MED também segue o caminho do dinheiro quando o golpista passa o valor para outras contas.",
    "Desconfie de quem oferece recuperar o seu dinheiro cobrando uma taxa: é outro golpe.",
]

FONTES = [
    ("Agência Brasil: nova regra do Pix amplia prazo para contestar golpe (set/2026)",
     "https://agenciabrasil.ebc.com.br/economia/noticia/2026-09/nova-regra-do-pix-amplia-prazo-para-contestar-golpe"),
    ("InfoMoney: passo a passo do novo mecanismo de devolução (nov/2025)",
     "https://www.infomoney.com.br/minhas-financas/pix-veja-passo-a-passo-de-novo-mecanismo-de-devolucao-de-dinheiro-em-caso-de-fraude/"),
]

PADRAO_JA_PAGUEI = re.compile(
    r"j[aá] paguei|j[aá] fiz o pix|fiz o pix|ca[ií] (no|num|em um|nesse|neste) golpe|"
    r"fui (v[ií]tima|enganad)|perdi (o |meu )?dinheiro|como (recupero|recuperar|pe[cç]o de volta)",
    re.IGNORECASE)


def parece_ja_paguei(texto):
    """Mensagem curta dizendo que a pessoa já pagou (e não uma mensagem de golpe colada)."""
    return len(texto.strip()) <= 120 and bool(PADRAO_JA_PAGUEI.search(texto))


def _ou(valor, padrao="(preencha)"):
    valor = (valor or "").strip()
    return valor if valor else padrao


def texto_para_o_banco(valor, quando, destino, relato):
    data = quando.strftime("%d/%m/%Y") if isinstance(quando, date) else _ou(quando)
    return (
        "Olá. Fui vítima de golpe e peço a abertura do MED (Mecanismo Especial de Devolução) "
        "para o Pix abaixo, com o bloqueio dos valores na conta de destino.\n\n"
        f"Valor: {_ou(valor)}\n"
        f"Data do Pix: {data}\n"
        f"Quem recebeu (nome ou chave Pix): {_ou(destino)}\n"
        f"O que aconteceu: {_ou(relato)}\n\n"
        "Guardei o comprovante e as conversas e vou registrar boletim de ocorrência."
    )


def texto_para_o_bo(valor, quando, destino, relato):
    data = quando.strftime("%d/%m/%Y") if isinstance(quando, date) else _ou(quando)
    return (
        f"Em {data}, fiz um Pix de {_ou(valor)} para {_ou(destino)}. "
        f"{_ou(relato, '(conte como foi o golpe)')} "
        "Depois percebi que se tratava de um golpe. Já pedi ao meu banco a abertura do MED "
        "(Mecanismo Especial de Devolução do Pix) e guardei o comprovante e as conversas."
    )


def preencher_a_partir_da_analise(ficha):
    """Usa os dados da última mensagem analisada para adiantar o formulário."""
    if not ficha:
        return {"valor": "", "destino": "", "relato": ""}
    chaves = ficha.get("chaves_pix") or []
    destino = ficha.get("quem_recebe") or (chaves[0] if chaves else "")
    quem = ficha.get("quem_diz_ser")
    relato = f"Recebi uma mensagem que usava o nome \"{quem}\" e pedia um pagamento." if quem else ""
    return {"valor": ficha.get("valor_pedido") or "", "destino": destino or "", "relato": relato}


def resposta_whatsapp():
    linhas = ["🆘 *Já pagou? Ainda dá para agir. Faça nesta ordem:*", ""]
    for i, (titulo, detalhe) in enumerate(PASSOS, 1):
        linhas.append(f"*{i}. {titulo}*\n{detalhe}")
        linhas.append("")
    linhas.append("*O que acontece depois*")
    linhas += [f"• {item}" for item in DEPOIS]
    linhas.append("")
    linhas.append("_No site do Desconfia.AI você gera um texto pronto para o banco e para o boletim de "
                  "ocorrência: desconfia-ai.streamlit.app_")
    return "\n".join(linhas)

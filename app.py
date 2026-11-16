# app.py
# Tela do Desconfia.AI, feita com Streamlit.
#
# Para rodar no computador (na pasta do projeto):  streamlit run app.py
# No Streamlit Community Cloud, a chave da OpenAI fica em Settings > Secrets.

import html
import os
from datetime import date

import streamlit as st

st.set_page_config(page_title="Desconfia.AI", page_icon="🛡️", layout="centered")

# A chave vem do arquivo .env (no computador) ou dos Secrets (no Streamlit Cloud)
if not os.getenv("OPENAI_API_KEY"):
    try:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass

from analise import EXEMPLO_GOLPE, EXEMPLO_LEGITIMO, analisar, juntar_sinais  # noqa: E402

MAX_CARACTERES = 3000   # mensagens maiores são cortadas, para proteger os créditos
MAX_ANALISES = 15       # limite de análises por visita, contra abuso da demo
MAX_POR_DIA = 400      # limite somando todas as visitas do dia, para proteger os créditos
EXEMPLOS = {EXEMPLO_GOLPE, EXEMPLO_LEGITIMO}

# ---------- Aparência ----------
st.markdown(
    """
    <style>
      html, body, [class*="css"] { font-size: 18px; }
      .block-container { padding-top: 2rem; max-width: 760px; }
      h1 { letter-spacing: -0.02em; }
      .sub { color: #4d5b6e; font-size: 1.1rem; margin: -0.4rem 0 1.2rem; }
      .faixa { border-radius: 14px; padding: 18px 20px; margin: 8px 0 18px; border: 2px solid; }
      .faixa h2 { margin: 0 0 6px; font-size: 1.6rem; }
      .faixa p { margin: 0; font-size: 1.05rem; }
      .alto  { background: #fbe9ec; border-color: #b3122a; color: #5c0816; }
      .medio { background: #fff4d6; border-color: #a86b00; color: #4a3000; }
      .baixo { background: #eaf0f6; border-color: #1f4fa8; color: #13233a; }
      .sinal { padding: 12px 0; border-bottom: 1px solid #c9d3de; }
      .sinal:last-child { border-bottom: none; }
      .trecho { display: block; margin-top: 4px; color: #4d5b6e; font-size: 0.95rem; }
      .trecho mark { background: #ffe15a; padding: 0 3px; color: #13233a; }
      .fazer { background: #13233a; color: #ffffff; border-radius: 14px; padding: 16px 20px; margin: 18px 0; }
      .fazer strong { display: block; font-size: 1.15rem; margin-bottom: 4px; }
      .dados td { padding: 6px 12px 6px 0; vertical-align: top; }
      .dados td:first-child { color: #4d5b6e; white-space: nowrap; }
    </style>
    """,
    unsafe_allow_html=True,
)

FAIXAS = {
    "alto": ("Risco alto", "Há sinais fortes de golpe. Não pague e não clique em links."),
    "medio": ("Risco médio", "Há sinais que pedem cuidado. Confirme pelo canal oficial antes de agir."),
    "baixo": (
        "Risco baixo",
        "Não encontramos sinais de golpe nesta mensagem. Isso não garante que ela seja "
        "verdadeira: confirme pelo canal oficial antes de pagar qualquer coisa.",
    ),
}


def e(texto):
    """Protege o texto antes de colocá-lo na página (a mensagem vem de fora)."""
    return html.escape(str(texto))


@st.cache_data(ttl=3600, show_spinner=False)
def analisar_exemplo(texto):
    """Os exemplos são sempre iguais: guardamos o resultado para economizar créditos."""
    return analisar(texto)


@st.cache_resource
def contador_do_dia():
    """Contador único do app inteiro (vale para todas as visitas)."""
    return {"dia": None, "total": 0}


def pode_analisar_hoje():
    contador = contador_do_dia()
    hoje = date.today().isoformat()
    if contador["dia"] != hoje:
        contador["dia"], contador["total"] = hoje, 0
    return contador["total"] < MAX_POR_DIA


def usar_exemplo(texto):
    st.session_state.mensagem = texto


# ---------- Topo ----------
st.title("Desconfia.AI")
st.markdown(
    '<p class="sub">Recebeu uma oferta de dinheiro estranha? Cole a mensagem aqui ou conte o que aconteceu. '
    "A gente aponta os sinais de golpe e diz o que fazer.</p>",
    unsafe_allow_html=True,
)

mensagem = st.text_area(
    "Mensagem recebida",
    key="mensagem",
    height=180,
    max_chars=MAX_CARACTERES,
    placeholder="Cole aqui a mensagem do WhatsApp, SMS ou e-mail que você recebeu. Também pode contar o que aconteceu, por exemplo uma ligação.",
)

col1, col2 = st.columns(2)
col1.button("Ver exemplo de golpe", on_click=usar_exemplo, args=(EXEMPLO_GOLPE,), width="stretch")
col2.button("Ver exemplo de mensagem normal", on_click=usar_exemplo, args=(EXEMPLO_LEGITIMO,), width="stretch")

analisar_agora = st.button("Analisar mensagem", type="primary", width="stretch")

# ---------- Análise ----------
if analisar_agora:
    texto = (mensagem or "").strip()
    usos = st.session_state.get("usos", 0)

    if not texto:
        st.warning("Cole uma mensagem na caixa acima para analisar.")
    elif usos >= MAX_ANALISES:
        st.warning("Você chegou ao limite de análises desta visita. Recarregue a página mais tarde para continuar.")
    elif texto not in EXEMPLOS and not pode_analisar_hoje():
        st.warning("O Desconfia.AI atingiu o limite de análises de hoje. Volte amanhã ou use os exemplos.")
    elif not os.getenv("OPENAI_API_KEY"):
        st.error("O Desconfia.AI está sem a chave de acesso à IA. Avise a equipe do projeto.")
    else:
        try:
            with st.spinner("Analisando a mensagem..."):
                ficha = analisar_exemplo(texto) if texto in EXEMPLOS else analisar(texto)
            st.session_state.usos = usos + 1
            if texto not in EXEMPLOS:
                contador_do_dia()["total"] += 1
            st.session_state.resultado = ficha
        except Exception:
            st.error("Não conseguimos analisar agora. Tente de novo em alguns segundos.")

ficha = st.session_state.get("resultado")
if ficha:
    titulo, frase = FAIXAS[ficha["nivel_de_risco"]]
    st.markdown(
        f'<div class="faixa {ficha["nivel_de_risco"]}" role="status">'
        f"<h2>{e(titulo)}</h2><p>{e(frase)}</p></div>",
        unsafe_allow_html=True,
    )

    if ficha.get("explicacao_simples"):
        st.markdown(e(ficha["explicacao_simples"]))

    sinais = juntar_sinais(ficha)
    if sinais:
        st.subheader("Por que desconfiar")
        partes = []
        for item in sinais:
            trecho = (
                f'<span class="trecho">Na mensagem: <mark>{e(item["trecho"])}</mark></span>'
                if item["trecho"]
                else ""
            )
            partes.append(f'<div class="sinal">{e(item["sinal"])}{trecho}</div>')
        st.markdown("".join(partes), unsafe_allow_html=True)

    if ficha.get("o_que_fazer"):
        st.markdown(
            f'<div class="fazer"><strong>O que fazer agora</strong>{e(ficha["o_que_fazer"])}</div>',
            unsafe_allow_html=True,
        )

    encontrados = [
        ("Diz ser", ficha.get("quem_diz_ser")),
        ("Quem recebe", ficha.get("quem_recebe")),
        ("Chave Pix", ", ".join(ficha.get("chaves_pix") or [])),
        ("Telefone", ", ".join(ficha.get("telefones") or [])),
        ("Site", ", ".join(ficha.get("sites") or [])),
        ("Valor pedido", ficha.get("valor_pedido")),
    ]
    linhas = [f"<tr><td>{e(r)}</td><td>{e(v)}</td></tr>" for r, v in encontrados if v]
    if linhas:
        st.subheader("O que encontramos na mensagem")
        st.markdown(f'<table class="dados">{"".join(linhas)}</table>', unsafe_allow_html=True)

st.divider()
st.caption(
    "O Desconfia.AI não dá veredito: mostra sinais de risco e o que fazer. "
    "Na dúvida, confirme sempre pelo canal oficial. A mensagem é enviada à IA da OpenAI para análise e nós não a guardamos. Evite colar senhas ou documentos. "
    "Projeto para o Hack Brasil 2026."
)

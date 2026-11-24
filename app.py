# app.py
# Tela do Desconfia.AI, feita com Streamlit.
#
# Para rodar no computador (na pasta do projeto):  streamlit run app.py
# No Streamlit Community Cloud, a chave da OpenAI fica em Settings > Secrets.

import hashlib
import html
import os
from pathlib import Path
from datetime import date

import streamlit as st

st.set_page_config(page_title="Desconfia.AI", page_icon="🛡️", layout="centered")

# Avisa o navegador que a página é em português, para o tradutor automático do Chrome não
# "traduzir" o texto e estragar as palavras (o Streamlit marca a página como inglês).
import streamlit.components.v1 as components  # noqa: E402

components.html(
    "<script>const raiz = window.parent.document.documentElement;"
    "raiz.lang = 'pt-BR'; raiz.setAttribute('translate', 'no');</script>",
    height=0,
)

# A chave vem do arquivo .env (no computador) ou dos Secrets (no Streamlit Cloud)
if not os.getenv("OPENAI_API_KEY"):
    try:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass

from analise import EXEMPLOS_PRONTOS, analisar, juntar_sinais, ler_imagem  # noqa: E402
from verificacoes import texto_dos_dias  # noqa: E402
from ja_paguei import (  # noqa: E402
    DEPOIS, FONTES, PASSOS, preencher_a_partir_da_analise, texto_para_o_banco, texto_para_o_bo,
)

MAX_CARACTERES = 3000   # mensagens maiores são cortadas, para proteger os créditos
MAX_ANALISES = 15       # limite de análises por visita, contra abuso da demo
MAX_POR_DIA = 400      # limite somando todas as visitas do dia, para proteger os créditos
MAX_PRINT_MB = 8       # tamanho máximo do print enviado
MAX_PRINTS = 5         # prints por visita (ler imagem custa uns 10 vezes mais que ler texto)
MAX_PRINTS_POR_DIA = 60  # prints somando todas as visitas do dia
EXEMPLOS = {texto for _, texto in EXEMPLOS_PRONTOS}

# ---------- Aparência ----------
st.markdown(
    """
    <style>
      html, body, [class*="css"] { font-size: 18px; }
      .block-container { padding-top: 2rem; max-width: 760px; }
      h1 { letter-spacing: -0.02em; }
      .sub { color: #4d5b6e; font-size: 1.1rem; margin: -0.4rem 0 1.2rem; }
      .faixa { border-radius: 14px; padding: 18px 20px; margin: 8px 0 18px; border: 2px solid; }
      #laudo { scroll-margin-top: 90px; }  /* a barra fixa do topo não cobre o título ao rolar */
      .faixa h2 { margin: 0 0 6px; font-size: 1.6rem; }
      .faixa p { margin: 0; font-size: 1.05rem; }
      .alto  { background: #fbe9ec; border-color: #b3122a; color: #5c0816; }
      .medio { background: #fff4d6; border-color: #a86b00; color: #4a3000; }
      .baixo { background: #eaf0f6; border-color: #1f4fa8; color: #13233a; }
      .sinal { padding: 12px 0; border-bottom: 1px solid #c9d3de; }
      .sinal:last-child { border-bottom: none; }
      .trecho { display: block; margin-top: 4px; color: #4d5b6e; font-size: 0.95rem; }
      .trecho a { color: #1f4fa8; }
      .trecho mark { background: #ffe15a; padding: 0 3px; color: #13233a; }
      .fazer { background: #13233a; color: #ffffff; border-radius: 14px; padding: 16px 20px; margin: 18px 0; }
      .fazer strong { display: block; font-size: 1.15rem; margin-bottom: 4px; }
      .dados td { padding: 6px 12px 6px 0; vertical-align: top; }
      .paguei { background: #eaf4ee; border-color: #1d6b45; color: #0f3d27; }
      .passos { padding-left: 1.3rem; margin: 6px 0 18px; }
      .passos li { margin: 0 0 14px; }
      .passos strong { display: block; font-size: 1.08rem; }
      .passos span { color: #4d5b6e; }
      .dados td:first-child { color: #4d5b6e; white-space: nowrap; }
      [data-testid="stFileUploaderDropzoneInstructions"] > div > span,
      [data-testid="stFileUploaderDropzoneInstructions"] > div > small { display: none; }
      [data-testid="stFileUploaderDropzoneInstructions"] > div::before {
        content: "Arraste o print aqui ou toque em Escolher print"; }
      [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] > * { display: none !important; }
      [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]::after { content: "Escolher print"; }
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


def versao_do_codigo():
    """Muda sempre que a análise muda, para o app não mostrar resultado antigo guardado."""
    soma = hashlib.md5()
    for nome in ("analise.py", "verificacoes.py"):
        soma.update(Path(__file__).with_name(nome).read_bytes())
    return soma.hexdigest()


class ResultadoSemIA(Exception):
    """Usada para não guardar na memória um resultado do modo de segurança."""

    def __init__(self, ficha):
        self.ficha = ficha


@st.cache_data(ttl=3600, show_spinner=False)
def analisar_exemplo(texto, versao):
    """Os exemplos são sempre iguais: guardamos o resultado para economizar créditos."""
    ficha = analisar(texto)
    if ficha.get("modo") == "seguranca":
        raise ResultadoSemIA(ficha)  # erro não é guardado: quando a IA voltar, sai o laudo completo
    return ficha


def analisar_mensagem(texto):
    if texto not in EXEMPLOS:
        return analisar(texto)
    try:
        return analisar_exemplo(texto, versao_do_codigo())
    except ResultadoSemIA as sem_ia:
        return sem_ia.ficha


@st.cache_resource
def contador_do_dia():
    """Contador único do app inteiro (vale para todas as visitas)."""
    return {"dia": None, "total": 0, "prints": 0}


def contador_de_hoje():
    contador = contador_do_dia()
    hoje = date.today().isoformat()
    if contador["dia"] != hoje:
        contador["dia"], contador["total"], contador["prints"] = hoje, 0, 0
    return contador


def pode_analisar_hoje():
    return contador_de_hoje()["total"] < MAX_POR_DIA


def data_br(iso):
    ano, mes, dia = iso.split("-")
    return f"{dia}/{mes}/{ano}"


def texto_da_consulta(v):
    if v["situacao"] == "registrado" and v["dias"] is not None:
        return f"registrado em {data_br(v['registrado_em'])}, há {texto_dos_dias(v['dias'])}."
    if v["situacao"] == "registrado":
        return "está registrado, mas o registro não informa a data."
    if v["situacao"] == "nao_registrado":
        return "não está registrado. Ninguém é dono desse endereço."
    return "não conseguimos consultar o registro agora."


MODO_ANALISE = "Recebi uma mensagem suspeita"
MODO_PAGUEI = "Já paguei, e agora?"


def ir_para_ja_paguei():
    st.session_state.modo = MODO_PAGUEI


def voltar_para_analise():
    st.session_state.modo = MODO_ANALISE


def rodape():
    st.divider()
    st.caption(
        "O Desconfia.AI não dá veredito: mostra sinais de risco e o que fazer. "
        "Na dúvida, confirme sempre pelo canal oficial. A mensagem é enviada à IA da OpenAI para análise e nós não a guardamos. Evite colar senhas ou documentos. "
        "Projeto para o Hack Brasil 2026."
    )


def mostrar_ja_paguei():
    st.markdown(
        '<div class="faixa paguei" role="status"><h2>Já pagou? Ainda dá para agir.</h2>'
        "<p>Faça nesta ordem. Quanto mais rápido, maior a chance de recuperar o dinheiro.</p></div>",
        unsafe_allow_html=True,
    )
    itens = "".join(f"<li><strong>{e(titulo)}</strong><span>{e(detalhe)}</span></li>" for titulo, detalhe in PASSOS)
    st.markdown(f'<ol class="passos">{itens}</ol>', unsafe_allow_html=True)

    st.subheader("Texto pronto para o banco e para o boletim")
    st.caption("Preencha o que souber. Esses dados não passam pela IA e não ficam guardados.")
    base = preencher_a_partir_da_analise(st.session_state.get("resultado"))
    valor = st.text_input("Quanto você pagou?", value=base["valor"], placeholder="Ex.: R$ 49,90", key="pg_valor")
    quando = st.date_input("Em que dia fez o Pix?", value=date.today(), max_value=date.today(),
                           format="DD/MM/YYYY", key="pg_data")
    destino = st.text_input("Para quem foi o Pix? (nome ou chave Pix)", value=base["destino"], key="pg_destino")
    relato = st.text_area("Como foi o golpe? (resumo curto)", value=base["relato"], height=90, key="pg_relato",
                          placeholder="Ex.: Recebi uma mensagem dizendo que eu tinha dinheiro para receber e paguei uma taxa.")

    st.markdown("**Para o banco** (cole no chat do app ou leia para o atendente):")
    st.code(texto_para_o_banco(valor, quando, destino, relato), language=None, wrap_lines=True)
    st.markdown("**Para o boletim de ocorrência:**")
    st.code(texto_para_o_bo(valor, quando, destino, relato), language=None, wrap_lines=True)
    st.caption("Para copiar, use o botão no canto de cada quadro.")

    st.subheader("O que acontece depois")
    st.markdown("\n".join(f"- {item}" for item in DEPOIS))
    st.caption("Fontes: " + " · ".join(f"[{nome}]({link})" for nome, link in FONTES))
    st.button("Voltar e analisar uma mensagem", on_click=voltar_para_analise, width="stretch")


def ler_print(arquivo):
    """Diminui o print (economiza créditos) e pede à IA para transcrever o texto."""
    conteudo = arquivo.getvalue()
    if len(conteudo) > MAX_PRINT_MB * 1024 * 1024:
        return None
    try:
        from io import BytesIO
        from PIL import Image
        imagem = Image.open(BytesIO(conteudo)).convert("RGB")
        imagem.thumbnail((1600, 1600))
        saida = BytesIO()
        imagem.save(saida, format="JPEG", quality=85)
        conteudo = saida.getvalue()
    except Exception:
        return None  # arquivo que não é imagem de verdade
    return ler_imagem(conteudo, "image/jpeg")


def limpar_tudo():
    """Apaga a mensagem, o print e o laudo, para começar de novo."""
    st.session_state.mensagem = ""
    st.session_state.versao_print = st.session_state.get("versao_print", 0) + 1
    st.session_state.resultado = None
    st.session_state.texto_do_print = None


def iniciar_analise():
    """Marca que uma análise começou: até ela terminar, botões e campos ficam travados."""
    st.session_state.analisando = True


def usar_exemplo(texto):
    """Coloca o exemplo na caixa e já analisa, sem precisar de outro clique."""
    st.session_state.mensagem = texto
    st.session_state.analisar_exemplo = True
    st.session_state.analisando = True


def avisar(texto, tipo="aviso"):
    """Guarda um aviso para mostrar quando a tela voltar (depois da análise)."""
    st.session_state.aviso = (tipo, texto)
    st.session_state.resultado = None


def mostrar_laudo(ficha):
    """Desenha o laudo de uma mensagem analisada."""
    titulo, frase = FAIXAS[ficha["nivel_de_risco"]]
    sem_ia = ficha.get("modo") == "seguranca"
    if sem_ia and ficha["nivel_de_risco"] == "baixo":
        frase = ("Nossas regras fixas não encontraram sinais clássicos de golpe, mas a análise completa está "
                 "indisponível agora. Não pague nada antes de confirmar pelo canal oficial.")
    st.markdown(
        f'<div class="faixa {ficha["nivel_de_risco"]}" id="laudo" role="status">'
        f"<h2>{e(titulo)}</h2><p>{e(frase)}</p></div>",
        unsafe_allow_html=True,
    )
    rolar = st.session_state.pop("rolar_para_laudo", None)
    if rolar:
        # Leva a tela até o laudo (no celular, o resultado pode ficar fora da tela)
        components.html(
            f"<script>/* {rolar} */ setTimeout(function () {{"
            "const el = window.parent.document.getElementById('laudo');"
            "if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); } }, 300);</script>",
            height=0,
        )
    if st.session_state.get("texto_do_print"):
        with st.expander("Texto que lemos no print"):
            st.text(st.session_state.texto_do_print)
    if sem_ia:
        st.info("**Modo de segurança.** A inteligência artificial está indisponível agora, então este laudo usa "
                "só as nossas regras fixas, a consulta oficial de domínios e a detecção de sites que imitam "
                "marcas. Tente de novo daqui a pouco para ter a análise completa.")

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

    verificacoes = ficha.get("verificacoes") or []
    if verificacoes:
        st.subheader("O que conferimos em fonte oficial")
        partes = []
        for v in verificacoes:
            partes.append(
                f'<div class="sinal"><strong>{e(v["site"])}</strong>: {e(texto_da_consulta(v))}'
                f'<span class="trecho">Fonte: <a href="{e(v["link"])}" target="_blank" rel="noopener">'
                f'{e(v["fonte"])}</a></span></div>'
            )
        st.markdown("".join(partes), unsafe_allow_html=True)
        st.caption("Um site antigo não quer dizer que seja confiável: golpistas também usam sites antigos que foram invadidos.")

    if ficha["nivel_de_risco"] in ("alto", "medio"):
        st.button("Já fiz o pagamento. E agora?", on_click=ir_para_ja_paguei, width="stretch")

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


def executar_analise(mensagem, veio_de_exemplo, chave_print):
    """Lê o print (se houver), analisa e guarda o resultado. Roda com a tela travada."""
    texto = (mensagem or "").strip()
    usos = st.session_state.get("usos", 0)
    arquivo = None if veio_de_exemplo else st.session_state.get(chave_print)

    if not texto and arquivo is None:
        avisar("Cole uma mensagem na caixa acima ou envie um print para analisar.")
        return
    if usos >= MAX_ANALISES:
        avisar("Você chegou ao limite de análises desta visita. Recarregue a página mais tarde para continuar.")
        return
    gasta_credito = arquivo is not None or texto not in EXEMPLOS
    if gasta_credito and not pode_analisar_hoje():
        avisar("O Desconfia.AI atingiu o limite de análises de hoje. Volte amanhã ou use os exemplos.")
        return
    if arquivo is not None and st.session_state.get("prints", 0) >= MAX_PRINTS:
        avisar("Você chegou ao limite de prints desta visita. Copie o texto da mensagem e cole na caixa acima.")
        return
    if arquivo is not None and contador_de_hoje()["prints"] >= MAX_PRINTS_POR_DIA:
        avisar("O limite de prints de hoje foi atingido. Copie o texto da mensagem e cole na caixa acima.")
        return

    # Conta no limite já no começo: assim ninguém gasta créditos cancelando análises no meio
    st.session_state.usos = usos + 1
    if gasta_credito:
        contador_de_hoje()["total"] += 1
    if arquivo is not None:
        st.session_state.prints = st.session_state.get("prints", 0) + 1
        contador_de_hoje()["prints"] += 1

    lido = None
    if arquivo is not None:
        with st.spinner("Lendo o print..."):
            lido = ler_print(arquivo)
        if lido is None:
            avisar("Não conseguimos ler esse print agora. Confira se é uma imagem de até "
                   f"{MAX_PRINT_MB} MB, ou copie o texto da mensagem e cole na caixa acima.")
            return
        if not lido:
            avisar("Não encontramos texto nesse print. Tente uma foto mais nítida ou cole o texto na caixa acima.")
            return
        texto = f"{texto}\n{lido}".strip()

    try:
        with st.spinner("Analisando a mensagem..."):
            ficha = analisar_mensagem(texto)
    except Exception:
        avisar("Não conseguimos analisar agora. Tente de novo em alguns segundos.", "erro")
        return
    st.session_state.resultado = ficha
    st.session_state.texto_do_print = lido
    if lido:  # o print já foi usado: na próxima mensagem, ele não entra junto
        st.session_state.versao_print = st.session_state.get("versao_print", 0) + 1
    st.session_state.rolar_para_laudo = st.session_state.usos


# ---------- Topo ----------
st.title("Desconfia.AI")
st.markdown(
    '<p class="sub">Recebeu uma oferta de dinheiro estranha? Cole a mensagem aqui ou conte o que aconteceu. '
    "A gente aponta os sinais de golpe e diz o que fazer.</p>",
    unsafe_allow_html=True,
)

ocupado = st.session_state.get("analisando", False)  # durante a análise, tudo fica travado

modo = st.radio("O que aconteceu?", [MODO_ANALISE, MODO_PAGUEI], key="modo", horizontal=True,
                label_visibility="collapsed", disabled=ocupado)
if modo == MODO_PAGUEI:
    mostrar_ja_paguei()
    rodape()
    st.stop()

mensagem = st.text_area(
    "Mensagem recebida",
    key="mensagem",
    height=180,
    max_chars=MAX_CARACTERES,
    disabled=ocupado,
    placeholder="Cole aqui a mensagem do WhatsApp, SMS ou e-mail que você recebeu. Também pode contar o que aconteceu, por exemplo uma ligação.",
)

CHAVE_PRINT = f"print_{st.session_state.get('versao_print', 0)}"
st.file_uploader(
    "Ou envie um print da mensagem",
    type=["png", "jpg", "jpeg", "webp"],
    key=CHAVE_PRINT,
    disabled=ocupado,
    help="A IA lê o texto do print e analisa. O print não fica guardado. Evite prints com senhas ou documentos.",
)

coluna_analisar, coluna_limpar = st.columns([3, 1])
coluna_analisar.button("Analisar mensagem", type="primary", width="stretch", on_click=iniciar_analise,
                       disabled=ocupado)
coluna_limpar.button("Limpar", on_click=limpar_tudo, width="stretch", disabled=ocupado)

area_laudo = st.container()  # o laudo aparece aqui, logo abaixo dos botões

st.caption("Não tem uma mensagem agora? Clique num exemplo pronto (todos são fictícios):")
colunas = st.columns(2)
for i, (nome, texto_exemplo) in enumerate(EXEMPLOS_PRONTOS):
    colunas[i % 2].button(nome, key=f"exemplo_{i}", on_click=usar_exemplo, args=(texto_exemplo,),
                          width="stretch", disabled=ocupado)

rodape()

# ---------- Análise ----------
# A tela inteira já foi desenhada com tudo travado. Só agora a análise roda; no fim, a tela
# é redesenhada com os botões liberados e o laudo no lugar.
if ocupado:
    with area_laudo:
        try:
            executar_analise(mensagem, st.session_state.pop("analisar_exemplo", False), CHAVE_PRINT)
        finally:
            st.session_state.analisando = False
    st.rerun()

with area_laudo:
    aviso = st.session_state.pop("aviso", None)
    if aviso:
        (st.error if aviso[0] == "erro" else st.warning)(aviso[1])
    if st.session_state.get("resultado"):
        mostrar_laudo(st.session_state.resultado)

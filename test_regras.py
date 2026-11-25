# test_regras.py
# Testes automáticos da parte que NÃO depende da IA: regras fixas, detecção de sites que imitam
# marcas, conferência dos trechos, modo "já paguei" e assinatura dos avisos do WhatsApp.
# Não usa a OpenAI nem a internet. Roda sozinho no GitHub a cada envio (aba Actions).
#
# Para rodar no computador:  python -m pytest -q test_regras.py

import csv
import hashlib
import hmac
from datetime import date
from pathlib import Path

from analise import (EXEMPLO_ALERTA, EXEMPLO_ENGANAR_IA, EXEMPLO_GOLPE, EXEMPLO_LEGITIMO, checar_regras,
                     juntar_sinais, sites_do_texto, trecho_existe)
from avaliar_planilha import montar_mensagem
from ja_paguei import parece_ja_paguei, texto_para_o_banco
from marcas import imitacoes

PLANILHA = Path(__file__).with_name("dados") / "testes_golpes.csv"


def categorias(mensagem):
    return {s["categoria"] for s in checar_regras(mensagem, sites_do_texto(mensagem))}


def linhas_da_planilha():
    return list(csv.DictReader(PLANILHA.open(encoding="utf-8-sig")))


def test_regras_nao_dao_alarme_falso_nas_mensagens_normais():
    for linha in linhas_da_planilha():
        if linha["Tipo de golpe"].lower().startswith("normal"):
            assert categorias(montar_mensagem(linha)) == set(), linha["ID"]
    assert categorias(EXEMPLO_LEGITIMO) == set()
    assert categorias(EXEMPLO_ALERTA) == set()


def test_regras_dos_golpes_mais_relatados():
    esperado = {"Falsa central": {"central", "conta_segura", "dados"}, "Falso parente": {"parente"}}
    for linha in linhas_da_planilha():
        tipo = linha["Tipo de golpe"]
        if tipo in esperado:
            assert categorias(montar_mensagem(linha)) & esperado[tipo], linha["ID"]


def test_golpe_do_governo_e_tentativa_de_enganar_a_ia():
    assert {"taxa", "dados", "site", "pressa"} <= categorias(EXEMPLO_GOLPE)
    assert "ia" in categorias(EXEMPLO_ENGANAR_IA)


def test_avisos_verdadeiros_nao_viram_golpe():
    assert categorias("O banco informa: nunca pedimos para transferir seu saldo para uma conta segura.") == set()
    assert categorias("Compra aprovada no cartão final 1234. Não reconhece? Ligue para o número no verso do seu cartão.") == set()
    assert categorias("Crédito pré-aprovado! Não cobramos nenhuma taxa antecipada.") == set()


def test_sites_que_imitam_marcas():
    achados = {a["site"]: a for a in imitacoes(["nubanck-seguranca.com", "banco-bradescco.com",
                                                 "magazineluiza-queima-estoque.com", "acordo-divida-seraza.com"])}
    assert achados["nubanck-seguranca.com"]["marca"] == "Nubank"
    assert achados["nubanck-seguranca.com"]["tipo"] == "erro"
    assert achados["banco-bradescco.com"]["oficial"] == "bradesco.com.br"
    assert achados["magazineluiza-queima-estoque.com"]["tipo"] == "nome"
    assert achados["acordo-divida-seraza.com"]["marca"] == "Serasa"
    # sites oficiais e palavras comuns não podem dar alarme
    assert imitacoes(["app.nubank.com.br", "valoresareceber.bcb.gov.br", "caixadesom.com.br",
                      "loja-caixa-de-som.com", "turismo-amazonas.com.br"]) == []


def test_email_nao_vira_site():
    assert sites_do_texto("Pague a taxa pela chave liberacao.valores@gmail.com") == set()


def test_trecho_inventado_e_recusado():
    mensagem = "Para liberar, pague a taxa de R$ 49,90 via Pix."
    assert trecho_existe("pague a taxa de R$ 49,90", mensagem)
    assert not trecho_existe("clique aqui agora", mensagem)


def test_juntar_sinais_nao_repete():
    ficha = {"sinais_regras": [{"categoria": "encurtador", "sinal": "Usa um link encurtado.", "risco": "medio"}],
             "sinais": [{"sinal": "O link encurtado esconde o endereço do site.", "trecho": "bit.ly/x"}]}
    assert len(juntar_sinais(ficha)) == 1


def test_modo_ja_paguei():
    assert parece_ja_paguei("já paguei")
    assert parece_ja_paguei("Caí no golpe, e agora?")
    assert not parece_ja_paguei("URGENTE! Pague a taxa de R$ 49,90 para liberar seu dinheiro. " * 3)
    texto = texto_para_o_banco("R$ 49,90", date(2026, 11, 20), "golpe@exemplo.com", "Paguei uma taxa falsa.")
    assert "MED" in texto and "R$ 49,90" in texto and "20/11/2026" in texto


def test_assinatura_dos_avisos_do_whatsapp(monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "segredo-de-teste")
    from bot_whatsapp import assinatura_valida
    corpo = b'{"entry": []}'
    assinatura = "sha256=" + hmac.new(b"segredo-de-teste", corpo, hashlib.sha256).hexdigest()
    assert assinatura_valida(corpo, assinatura)
    assert not assinatura_valida(corpo, "sha256=" + "0" * 64)
    assert not assinatura_valida(corpo, None)


def test_modo_de_seguranca_sem_ia(monkeypatch):
    """Se a IA cair, o laudo sai mesmo assim, só com as regras fixas."""
    import analise
    monkeypatch.setenv("FORCAR_MODO_SEGURANCA", "1")
    monkeypatch.setattr(analise, "consultar_sites", lambda sites, ignorar=(): [])
    golpe = analise.analisar(EXEMPLO_GOLPE)
    assert golpe["modo"] == "seguranca" and golpe["nivel_de_risco"] == "alto"
    assert golpe["explicacao_simples"] and golpe["o_que_fazer"]
    assert golpe["valor_pedido"] == "R$ 49,90"
    assert "liberacao.valores@gmail.com" in golpe["chaves_pix"]
    assert golpe["quem_diz_ser"] == "Valores a Receber (Banco Central)"
    normal = analise.analisar(EXEMPLO_LEGITIMO)
    assert normal["modo"] == "seguranca" and normal["nivel_de_risco"] == "baixo"


def test_exemplos_prontos_do_app():
    from analise import EXEMPLO_CENTRAL, EXEMPLO_EMPRESTIMO, EXEMPLO_MARCA, EXEMPLO_PARENTE
    assert "parente" in categorias(EXEMPLO_PARENTE)
    assert "central" in categorias(EXEMPLO_CENTRAL)
    assert "emprestimo" in categorias(EXEMPLO_EMPRESTIMO)
    assert "imitacao" in categorias(EXEMPLO_MARCA)


def test_sinais_em_formato_diferente_nao_quebram():
    ficha = {"sinais": ["Pede uma taxa para liberar dinheiro.", {"sinal": "Cria pressa.", "trecho": "só hoje"}, 3, None]}
    assert [i["sinal"] for i in juntar_sinais(ficha)] == ["Pede uma taxa para liberar dinheiro.", "Cria pressa."]


def test_falsa_caridade_por_link_desconhecido():
    assert "doacao" in categorias("Participe da minha vaquinha: http://vaquinha-casa-propria.com/")
    assert "doacao" in categorias("Ajude doando qualquer quantia: https://ajude-o-rafael.com/")
    assert "doacao" not in categorias("Participe da minha vaquinha: https://www.vakinha.com.br/123456")
    assert "doacao" not in categorias("Ajude doando qualquer quantia para a festa da escola.")


def test_print_sem_ia_nao_quebra(monkeypatch):
    """Sem a IA, o print não é lido (devolve None) e o app pede para colar o texto."""
    from analise import ler_imagem
    monkeypatch.setenv("FORCAR_MODO_SEGURANCA", "1")
    assert ler_imagem(b"qualquer coisa", "image/png") is None


def test_sinal_de_site_nao_oficial_nao_repete():
    ficha = {"sinais_regras": [{"categoria": "marca_site", "risco": "alto",
                                "sinal": "A mensagem usa o nome \"Correios\", mas o link x.com não é o site oficial."}],
             "sinais": [{"sinal": "O site mencionado não parece ser o oficial dos Correios.", "trecho": "x.com"}]}
    assert len(juntar_sinais(ficha)) == 1


def test_sinal_de_site_do_governo_nao_repete():
    ficha = {"sinais_regras": [{"categoria": "site", "risco": "alto",
                                "sinal": "Usa o nome do governo, mas o site x.com não é um endereço oficial."}],
             "sinais": [{"sinal": "O site x.com não é oficial do governo.", "trecho": "x.com"}]}
    assert len(juntar_sinais(ficha)) == 1


PAGINA_FALSA = {"ok": True, "titulo": "Nubank - Acesse sua conta", "destino": "https://nubanck-seguranca.com/login",
                "endereco": "https://nubanck-seguranca.com/login", "captura": None,
                "texto": "Digite seu CPF e sua senha. Informe o número do cartão e o CVV."}


def test_pagina_do_link():
    import pagina
    msg = "Confirme seus dados em nubanck-seguranca.com/login agora."
    assert pagina.escolher_link(msg, sites_do_texto(msg)) == "https://nubanck-seguranca.com/login"
    assert pagina.escolher_link("Veja em https://www.nubank.com.br", {"nubank.com.br"}) is None
    assert {s["categoria"] for s in pagina.sinais_da_pagina(PAGINA_FALSA)} == {"pagina", "imitacao"}
    assert pagina.sinais_da_pagina({"ok": False}) == [] and pagina.sinais_da_pagina(None) == []
    loja = {"ok": True, "titulo": "Bolos da Ana", "destino": "https://bolosdaana.com", "texto": "Encomende seu bolo."}
    assert pagina.sinais_da_pagina(loja) == []
    # página legítima que cita marcas no texto e tem "Esqueci minha senha": não pode dar alarme
    reclamacoes = {"ok": True, "titulo": "Black Friday", "destino": "https://www.reclameaqui.com.br/",
                   "texto": "Empresas mais reclamadas: Mercado Livre, Magazine Luiza. Entrar. Esqueci minha senha. "
                            "Pesquise a empresa pelo CPF ou CNPJ."}
    assert pagina.sinais_da_pagina(reclamacoes) == []


def test_sem_chave_da_firecrawl_nao_abre(monkeypatch):
    import pagina
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    assert pagina.abrir_pagina("https://exemplo.com") is None


def test_analise_com_pagina_do_link(monkeypatch):
    import analise
    import pagina
    monkeypatch.setenv("FORCAR_MODO_SEGURANCA", "1")
    monkeypatch.setattr(analise, "consultar_sites", lambda sites, ignorar=(): [])
    monkeypatch.setattr(pagina, "abrir_pagina", lambda endereco: PAGINA_FALSA)
    ficha = analise.analisar("Oi, tudo bem? Veja isso: nubanck-seguranca.com/login", abrir_pagina=True)
    assert ficha["nivel_de_risco"] == "alto"
    assert ficha["pagina"]["pede"] and ficha["pagina"]["marca"] == "Nubank"
    assert "pagina" not in analise.analisar("Oi, tudo bem? Veja isso: nubanck-seguranca.com/login")


def test_pagina_com_titulo_em_lista_nao_quebra(monkeypatch):
    import analise
    import pagina
    monkeypatch.setenv("FORCAR_MODO_SEGURANCA", "1")
    monkeypatch.setattr(analise, "consultar_sites", lambda sites, ignorar=(): [])
    estranha = dict(PAGINA_FALSA, titulo=["Nubank - Acesse sua conta", "outro"], destino=None)
    assert pagina.sinais_da_pagina(dict(estranha, titulo=pagina._texto(estranha["titulo"])))
    monkeypatch.setattr(pagina, "abrir_pagina", lambda endereco: estranha)  # formato inesperado
    ficha = analise.analisar("Veja: algum-site-qualquer.com/x", abrir_pagina=True)
    assert ficha["nivel_de_risco"] in ("baixo", "medio", "alto")  # o laudo sai mesmo assim

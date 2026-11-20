# testes_golpes.py
# Testa o Desconfia.AI com os 8 tipos de golpe mais relatados e com mensagens normais.
#
# Todas as mensagens são fictícias: nomes, valores, sites e lojas foram inventados.
# Um golpe "passa" quando o risco sai médio ou alto. Uma mensagem normal "passa" quando sai baixo.
#
# Como rodar (na pasta do projeto, com a chave da OpenAI no arquivo .env):
#     python testes_golpes.py
# Custo aproximado: menos de 1 centavo de dólar por rodada.

try:
    # No Windows, usa os certificados do próprio sistema (resolve erro de certificado
    # quando um antivírus ou a rede inspecionam as conexões). Instale com: pip install truststore
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from analise import EXEMPLO_ALERTA, EXEMPLO_GOLPE, EXEMPLO_LEGITIMO, analisar, juntar_sinais

GOLPES = [
    ("Falsa venda",
     "Promoção relâmpago! iPhone 15 de R$ 6.999 por R$ 1.299 na nossa loja do Instagram. "
     "Pagamento só no Pix para garantir o desconto, entrega em 24h. Restam só 3 unidades!"),
    ("Falsa central do banco",
     "Me ligaram dizendo que eram da central de segurança do meu banco. Falaram que tinha uma "
     "compra suspeita de R$ 2.890 no meu cartão e que eu precisava transferir meu saldo para uma "
     "conta segura enquanto eles resolviam."),
    ("Falso parente",
     "Oi mãe, troquei de número, esse é o novo, salva aí. Tô precisando pagar um boleto urgente "
     "hoje, consegue fazer um Pix de R$ 950 pra mim? Amanhã te devolvo."),
    ("Falso programa do governo", EXEMPLO_GOLPE),
    ("Falso emprego / tarefas pagas",
     "Olá! Vaga de meio período: ganhe de R$ 300 a R$ 800 por dia só curtindo vídeos. Para "
     "começar, faça um depósito de ativação de R$ 50. Vagas limitadas, responda agora."),
    ("Falso investimento",
     "Invista R$ 500 e receba R$ 5.000 em 7 dias com o nosso robô de criptomoedas. "
     "Rendimento garantido de 30% ao mês. Vagas limitadas!"),
    ("Falso empréstimo",
     "Empréstimo aprovado de R$ 15.000 mesmo para negativados! Para liberar o crédito, pague a "
     "taxa de seguro de R$ 350 via Pix para a Crédito Fácil Financeira."),
    ("Boleto falso",
     "Sua conta de luz está atrasada e a energia será cortada hoje. Pague o boleto atualizado "
     "no link bit.ly/conta-luz-2026 para evitar o corte."),
]

NORMAIS = [
    ("Fatura do banco", EXEMPLO_LEGITIMO),
    ("Alerta verdadeiro sobre golpe", EXEMPLO_ALERTA),
    ("Aviso verdadeiro do banco",
     "O banco informa: nunca pedimos para transferir seu saldo para uma conta segura e não "
     "ligamos pedindo sua senha. Em caso de dúvida, ligue para o número do seu cartão."),
    ("Recado de comércio",
     "Oi, aqui é a Ana da padaria. Seu pedido de bolo para sábado ficou em R$ 85. "
     "Pode pagar na retirada, tá bom?"),
]


def rodar():
    resultados = []
    for grupo, lista, passa in (("golpe", GOLPES, ("medio", "alto")), ("normal", NORMAIS, ("baixo",))):
        for nome, mensagem in lista:
            ficha = analisar(mensagem)
            risco = ficha["nivel_de_risco"]
            ok = risco in passa
            resultados.append(ok)
            print(f"{'OK  ' if ok else 'ERRO'} | {grupo:6} | {nome:30} | risco {risco}")
            for item in juntar_sinais(ficha)[:4]:
                print(f"       - {item['sinal']}")
    acertos = sum(resultados)
    print(f"\nAcertos: {acertos} de {len(resultados)}")


if __name__ == "__main__":
    rodar()

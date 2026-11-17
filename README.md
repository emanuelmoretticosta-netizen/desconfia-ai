# Desconfia.AI

**A IA que desconfia por você!** Antes de pagar, confira. Se já pagou, recupere.

Projeto para o Hack Brasil 2026, trilha de **Cibersegurança**.

> Status: em desenvolvimento durante o hackathon (04/11 a 30/11/2026).

## O problema:

Golpes financeiros digitais estão em alta no Brasil e chegam principalmente pelo WhatsApp, Instagram e Facebook:

- falsos investimentos com rendimento "garantido";
- empréstimos fáceis que exigem uma "taxa de liberação";
- falsos programas do governo, como Valores a Receber e Desenrola Brasil.

Em um levantamento com 16 mil anúncios que citavam "empréstimo" nas plataformas da Meta, **52% tinham indícios de fraude**. Quem mais cai não sabe diferenciar uma oferta oficial de uma falsa. E quem já pagou, muitas vezes, nem sabe que existe um caminho oficial para pedir o dinheiro de volta.

## A solução:

A pessoa cola a mensagem suspeita e, em segundos, recebe um **laudo em linguagem simples**, com provas tiradas de **fontes oficiais**, e não só a opinião de uma IA.

### Exemplo (fictício):

**Mensagem recebida:**

> URGENTE! Você tem R$ 1.847,32 no Valores a Receber do Banco Central. Para liberar, pague a taxa de R$ 49,90 via Pix e informe seu CPF e o nome da sua mãe em www.valores-receber-brasil.com. Válido só hoje!

**Laudo do Desconfia.AI:**

> **Risco alto. Não pague.**
> - O Valores a Receber oficial **nunca cobra taxa** e só funciona no site do Banco Central.
> - O site informado **não é um endereço do governo**.
> - A mensagem pede **CPF e nome da mãe**, dados usados para roubo de identidade.
> - Usa **urgência** ("válido só hoje"), tática comum de golpe.
>
> **O que fazer:** não clique no link. Para consultar valores a receber, use apenas o site oficial do Banco Central.

## Como funciona:

1. **Entrada:** a pessoa cola o texto da oferta (em breve, também link e print).
2. **Extração com IA:** identificamos empresa, CNPJ, chave Pix, telefone, site e programa citado.
3. **Checagem em fontes oficiais:**
    - **Banco Central:** a empresa está autorizada a funcionar? ([dados abertos do BCB](https://dadosabertos.bcb.gov.br/))
    - **CVM:** a empresa ou pessoa está impedida de atuar no mercado ou tem alerta?
    - **CNPJ:** existe, está ativo, há quanto tempo?
    - **Programas oficiais:** a oferta contradiz as regras do programa real?
4. **Laudo:** nível de risco, sinais encontrados, fontes e o que fazer.
5. **Modo "já paguei":** passo a passo para pedir a devolução pelo **MED** (Mecanismo Especial de Devolução do Pix) no app do banco, mais um **dossiê com as evidências** para o banco e para a denúncia.

## Princípios:

- **Nunca dizemos "seguro".** Golpes novos podem não ter registro em lugar nenhum. Mostramos sinais de risco e orientamos a confirmar pelo canal oficial.
- **Provas, não achismo.** Cada conclusão vem acompanhada da fonte.
- **Ensinar a reconhecer.** O laudo explica *por que* algo é suspeito, para a pessoa identificar o padrão da próxima vez.
- **Privacidade.** Não guardamos dados pessoais de quem consulta.

## O que nos diferencia:

| Solução existente | Limitação | Desconfia.AI |
| --- | --- | --- |
| Apps que dizem se uma mensagem "parece golpe" | Só a opinião da IA, sem provas | Cruza com dados oficiais do Banco Central e da CVM |
| Questionários de risco | A pessoa precisa responder tudo sozinha | Lê a oferta automaticamente |
| Bloqueio de chaves Pix pelos bancos | Só age na hora do pagamento e depois de denúncias | Age antes, no momento em que a oferta chega |
| Nenhuma | Quem já caiu fica sem orientação | Guia a recuperação pelo MED e gera o dossiê |

## Tecnologias

- **Python**
- **Streamlit** (interface web)
- **API da OpenAI** (extração e explicação)
- **Dados abertos do Banco Central e da CVM**
- **Consulta pública de CNPJ**

## Como executar:

```bash
git clone https://github.com/emanuelmoretticosta-netizen/desconfia-ai.git
cd desconfia-ai
pip install -r requirements.txt
```

Crie um arquivo `.env` na pasta do projeto com sua chave da OpenAI:

```
OPENAI_API_KEY=sua_chave_aqui
```

Instruções para rodar a interface serão adicionadas assim que ela estiver pronta.

## Próximos passos:

- Análise de links e prints, não só de texto
- Canal no WhatsApp para encaminhar mensagens suspeitas
- Detecção de campanhas: a mesma chave Pix ou telefone em várias ofertas diferentes
- Classificador próprio em português (BERTimbau) com taxa de acerto medida

## Aviso!

Todos os exemplos de golpe usados neste repositório são fictícios ou baseados em casos públicos noticiados. Nenhum dado pessoal real de terceiros é armazenado. O Desconfia.AI não substitui a orientação do seu banco ou dos órgãos oficiais.

## Time:

- Emanuel Moretti Costa
- Maria Clara de Andrade e Silva

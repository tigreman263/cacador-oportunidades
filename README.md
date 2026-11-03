# Caçador de Oportunidades

Bot pessoal que procura anúncios no **OLX** e no **CustoJusto** (motas, carros, casas, terrenos, outras coisas),
calcula o **preço normal** de mercado (mediana) de cada procura e avisa no **Telegram** quando aparece algo bem abaixo desse preço.
O WhatsApp (CallMeBot) também funciona, como canal opcional.

- **Boas compras**: sem problemas e com desconto suficiente.
- **A rever**: com um problema declarado ("não pega", "para recuperar"), mas com um desconto que pode compensar.

Tudo corre de graça no GitHub: o bot no **GitHub Actions** (de 15 em 15 minutos) e a página no **GitHub Pages**.
A página serve para ver os anúncios e mudar as regras e procuras a partir do telemóvel.

## Estrutura

```
config.json                 procuras e regras escolhidas (a página grava aqui)
docs/                       página publicada no GitHub Pages
  index.html                a página
  regras.json               explicação e proposta de cada regra/campo
  dados.json                anúncios e preço de mercado (escrito pelo bot)
  localidades.json          distritos, concelhos e lugares (dados GeoNames)
estado/estado.json          histórico de preços e alertas já enviados (memória do bot)
bot/                        o bot em Python
  fontes/olx.py             OLX (API das listagens do site)
  fontes/custojusto.py      CustoJusto (JSON da página)
  analise.py                filtros, preço normal e classificação
  zonas.py                  "Onde procurar": país, raio em km, concelhos/distritos
  avisos.py                 texto dos alertas e envio para os canais configurados
  telegram.py / whatsapp.py canais de alerta
.github/workflows/cacador.yml   agendamento de 15 em 15 minutos
tests/                      testes automáticos
```

## 1. Testar no computador

Precisas de Python 3.12 ou mais recente.

```
pip install -r requirements.txt
python -m unittest discover -s tests -t .   # testes automáticos
python -m bot --sem-avisos                  # verificação real: pesquisa e mostra os alertas no ecrã
```
A verificação real grava `docs/dados.json` e `estado/estado.json`. Se quiseres começar do zero antes de publicar,
apaga `estado/estado.json` e põe em `docs/dados.json` o conteúdo `{"atualizado": null, "anuncios": {}, "mercado": {}}`.

**A página:**
- abrir `docs/index.html` diretamente mostra os **dados de exemplo**;
- para ver os dados reais da pasta `docs/`, corre `python -m http.server 8000 -d docs` e abre <http://localhost:8000/?real>.

## 2. Criar o bot do Telegram

1. No Telegram, abre o **@BotFather**, envia `/newbot`, escolhe um nome (ex.: *Caçador de Oportunidades*)
   e um utilizador terminado em `bot` (ex.: `cacador_telmo_bot`). O BotFather responde com um **token**.
2. Abre o teu bot novo, carrega em **Iniciar** e envia-lhe "olá".
3. No computador, cria um ficheiro `.env` na raiz do projeto (o `.gitignore` impede que vá para o GitHub):
   ```
   TELEGRAM_TOKEN=123456789:AA...o-teu-token
   ```
4. Corre `python -m bot --telegram-teste`. Aparece o teu **chat id** (um número). Junta-o ao `.env`:
   ```
   TELEGRAM_CHAT_ID=123456789
   ```
5. Corre outra vez `python -m bot --telegram-teste`. Deve chegar "✅ Caçador de Oportunidades ligado".

Para receber num **grupo** (ex.: partilhado com alguém): adiciona o bot ao grupo, envia lá uma mensagem
e usa o id do grupo (começa por `-`). Para vários destinos, separa os ids por vírgula.

## 3. Alojar no GitHub (grátis)

1. **Criar o repositório** (ex.: `cacador-oportunidades`) e enviar esta pasta:
   ```
   git init -b main
   git add .
   git commit -m "Primeira versão"
   gh repo create cacador-oportunidades --public --source . --push
   ```
   O GitHub Pages grátis exige repositório **público**. Isso torna visíveis o `config.json` (o que procuras e a tua zona)
   e os anúncios encontrados. Os tokens **nunca** vão para o repositório.

2. **Segredos**: Settings → Secrets and variables → Actions → *New repository secret*:
   `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`, com os mesmos valores do `.env`.
   Ou, pela linha de comandos: `gh secret set TELEGRAM_TOKEN` e `gh secret set TELEGRAM_CHAT_ID`.

3. **Página**: Settings → Pages → *Deploy from a branch* → `main` / `/docs`.
   Fica em `https://<utilizador>.github.io/cacador-oportunidades/`.

4. **Primeira execução**: separador Actions → *Caçador de Oportunidades* → *Run workflow* (ou `gh workflow run cacador.yml`).
   Abre a execução e confirma no registo quantos anúncios cada fonte devolveu.
   Depois disto, corre sozinho de 15 em 15 minutos.

5. **Ligar a página ao GitHub** para gravar regras a partir do telemóvel:
   GitHub → Settings → Developer settings → *Fine-grained tokens* → *Generate new token*,
   *Repository access*: só este repositório, *Permissions*: **Contents: Read and write**.
   Na página, separador **Regras** → *Ligação ao GitHub*, cola o token. Fica guardado só nesse telemóvel.

**WhatsApp (opcional):** segue <https://www.callmebot.com/blog/free-api-whatsapp-messages/> e cria os segredos
`WHATSAPP_TELEFONE` (ex.: `+351912345678`) e `WHATSAPP_APIKEY`. Se os dois canais estiverem configurados, recebes nos dois.

## Como decide

1. **Filtro de palavras** (no título): todas as *palavras obrigatórias*, pelo menos uma das *alternativas*, nenhuma *palavra a ignorar*.
   As palavras a ignorar valem também para a categoria do site: `pecas` afasta tudo o que esteja em "Peças e acessórios".
   *Problemas graves* (título ou descrição) descartam o anúncio de vez.
2. **Preço comparável**: preço total, ou preço por m² nas casas e terrenos (anúncios sem área ficam de fora).
3. **Preço normal**: mediana dos anúncios sem problemas vistos nos últimos 120 dias, **do mesmo grupo** (um T2 só com T2, um 250 só com 250).
   Só compara quando há pelo menos *Anúncios necessários para conhecer o mercado*.
   Nas casas e terrenos, o mercado é só o da zona escolhida (o preço por m² varia muito de região para região).
4. **Classificação**
   - com problema razoável e desconto ≥ *desconto mínimo para anúncios com problemas* → **A rever**;
   - sem problemas, abaixo do *limite de burla* → ignorado (bom demais para ser verdade);
   - sem problemas e desconto ≥ *desconto mínimo* (menos a *folga* se houver sinais de pressa) → **Boa compra**.
5. **Alertas**: cada anúncio é avisado uma vez; volta a ser avisado se baixar de preço.

## Limitações conhecidas

- **As fontes não são APIs oficiais.** Podem mudar ou bloquear pedidos automáticos a qualquer momento.
  O bot identifica-se honestamente, faz poucos pedidos e, quando uma fonte falha, regista um aviso e continua com as outras.
  Confirma que este uso respeita os termos de cada site.
  - Em 2026-11-03, a partir de um PC em Portugal: **o CustoJusto respondeu** (cerca de 40 anúncios por pesquisa)
    e **o OLX recusou (HTTP 403)**. Do GitHub Actions o resultado pode ser diferente: confirma no registo da primeira execução.
- **A pesquisa é nacional** (os anúncios mais recentes) e a zona é filtrada depois.
  Para casas e terrenos numa zona pequena, põe o nome da terra no *Texto de pesquisa* (ex.: `moradia tomar`).
- **O mercado demora a aprender**: nos primeiros dias não há alertas, até haver amostras suficientes.
- **Um commit por verificação** (o `dados.json` muda sempre): cerca de 100 commits por dia no repositório.
- Os dados de localidades vêm do [GeoNames](https://www.geonames.org) (licença CC BY 4.0).

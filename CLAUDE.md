# Caçador de Oportunidades — contexto para o Claude Code

Responde sempre em **português de Portugal**. O utilizador não é programador:
explica os passos de forma simples e confirma antes de ações irreversíveis
(apagar ficheiros, `git push --force`, mexer em Secrets).

## O que é

Bot que vigia o CustoJusto (e o AutoUncle, para carros) e avisa por **Telegram** (WhatsApp/CallMeBot
opcional) **só de boas compras**: anúncios claramente abaixo do preço normal de
mercado, que o próprio bot aprende com os anúncios que vai vendo. Corre no GitHub
Actions; quem o acorda de 15 em 15 min é um Worker do Cloudflare (`extras/cloudflare/`),
porque o agendador do GitHub salta muitas execuções (o `schedule` fica de reserva, 1×/hora). Tem uma página (GitHub Pages, pasta `docs/`) com
listagem e configurações.

## Decisões do utilizador (respeitar)

- Só **boas compras**, não apenas "dentro do preço".
- Anúncios com problemas **não se descartam**: vão para a lista "A rever"
  (se o desconto compensar). Prioridade sempre para anúncios sem problemas.
  Só os "problemas graves" definidos pelo utilizador são descartados.
- Todas as regras são editáveis na página, **sempre com descrição e proposta**
  ("Usar proposta") para quem não sabe o que pôr.
- Várias procuras ao mesmo tempo, por tipo: mota, carro, casa, terreno, outro.
  Casas e terrenos comparam **preço por m²**.
- Zonas escolhidas de uma **lista** (sem escrever à mão): todo o país, raio em km
  a partir de uma localidade, ou concelhos/distritos.
- **Não** desenvolver recolha de notícias aqui. Esta ferramenta é separada do
  Argos (investimentos) e dos bots de cripto; no futuro haverá um painel comum
  que só lê o estado de cada ferramenta.
- Frequência de procura escolhida no painel (regra `intervalo_minutos`, mínimo 15 min,
  o despertador toca de 15 em 15 min e o bot salta as execuções antes da altura).
- Alertas por **Telegram** (decisão de 2026-11-03; antes era WhatsApp).

## Estrutura

- `bot/__main__.py` — entrada: `python -m bot` (opções `--sem-avisos`, `--telegram-teste`, `--localidades`)
- `bot/cacador.py` — ciclo: ler fontes → filtrar → mercado → classificar → gravar; `processar()` não usa rede (testável)
- `bot/analise.py` — filtros de palavras, mediana por grupo, categorias boa / rever
- `bot/zonas.py` — localização dos anúncios e filtro de zona (país, raio, lista)
- `bot/localidades.py` — cria `docs/localidades.json` a partir do GeoNames (CC BY)
- `bot/fontes/custojusto.py` — JSON `__NEXT_DATA__` da página de pesquisa (com categoria por procura)
- `bot/fontes/autouncle.py` — carros de vários sites (schema.org ld+json); sem pesquisa por texto: tipo de carro (`categoria_autouncle`) + teto de preço
- `bot/fontes/drive.py` — "Base do Drive": CSVs que o utilizador junta à mão no Google Drive
  (`OLX/base/<distrito>/<concelho>/<família>.csv`, separador `;`). Cada procura escolhe as famílias
  (`familias_drive`); o bot só lê essas. Nunca vai ao site do OLX: só lê os ficheiros. Cópia local em
  `estado/drive_cache` (fora do Git, guardada com `actions/cache`), só descarrega o que mudou.
- `bot/avisos.py`, `bot/telegram.py`, `bot/whatsapp.py` — texto e envio dos alertas
- `config.json` — regras e procuras do utilizador (a página grava aqui via API do GitHub)
- `docs/regras.json` — descrições, propostas e modelos por tipo
- `docs/index.html` — página (Boas, A rever, Procuras, Regras); `?demo` / `?real`
- `docs/dados.json`, `estado/estado.json` — gerados pelo bot
- `.github/workflows/cacador.yml` — agendamento e gravação do estado
- `tests/` — `python -m unittest discover -s tests -t .`

Segredos: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `GOOGLE_DRIVE_CHAVE` (JSON da conta de serviço Google, com a pasta OLX partilhada só para leitura) (opcional: `WHATSAPP_TELEFONE`, `WHATSAPP_APIKEY`).

## Estado (2026-11-03)

- O bot antigo (pacote `cacador/`) ficou guardado no ramo `bot-antigo`. Nunca
  chegou a recolher anúncios: o OLX dava 403 e o leitor do CustoJusto falhava.
- **CustoJusto funciona** (cerca de 40 anúncios por pesquisa). Campos reais:
  `title`, `price`, `body`, `listID`, `url` (`/<distrito>/<categoria>/.../<anuncio>`),
  `locationNames.county` (concelho), `locationNames.parish`, `params.size` (área).
  As "palavras a ignorar" também se aplicam à categoria do link (`pecas` afasta peças).
- **OLX responde 403** a pedidos automáticos, tanto do PC como do GitHub Actions.
  Em 2026-11-07, a pedido do utilizador, **tudo o que era OLX foi apagado** (leitor,
  botões "Abrir/Ver no OLX", opção nos Sites). Não contornar a deteção de bots.
  O utilizador quer testar outra abordagem mais tarde.
- O CustoJusto, quando a pesquisa tem poucos resultados, enche a página com
  "destaques" de outras categorias; o bot ignora-os (`da_categoria`).

## Cuidados

- Nunca pôr tokens, número de telefone ou chaves no repositório:
  só em Secrets do GitHub ou no `.env` (que está no `.gitignore`).
- Com o repositório público, a página e o `config.json` ficam públicos. Não
  escrever dados pessoais do utilizador (morada, localidade) em ficheiros de
  exemplo ou documentação.
- Frequências moderadas nos sites; respeitar os termos de utilização.

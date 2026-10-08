# Caçador de Oportunidades — contexto para o Claude Code

Responde sempre em **português de Portugal**. O utilizador não é programador:
explica os passos de forma simples e confirma antes de ações irreversíveis
(apagar ficheiros, `git push --force`, mexer em Secrets).

## O que é

Bot que vigia o OLX e o CustoJusto e avisa por WhatsApp (CallMeBot) **só de boas
compras**: anúncios claramente abaixo do preço normal de mercado, que o próprio
bot aprende com os anúncios que vai vendo. Corre no GitHub Actions de 15 em 15
min (alternativa: Raspberry Pi com cron). Tem uma página (GitHub Pages, pasta
`docs/`) com listagem e configurações.

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
- Alertas por WhatsApp via CallMeBot.

## Estrutura

- `cacador/main.py` — ciclo principal (ler fontes → filtrar → avaliar → alertar → gravar)
- `cacador/avaliar.py` — categorias boa / rever / descartado; mediana robusta
- `cacador/config.py` — junta `config.json` com as propostas de `docs/regras.json`
- `cacador/localidades.py` — base GeoNames (CC-BY), geolocalização e distâncias
- `cacador/fontes/olx.py` — endpoint JSON `https://www.olx.pt/api/v1/offers/`
- `cacador/fontes/custojusto.py` — página de pesquisa (JSON `__NEXT_DATA__` ou HTML)
- `cacador/notificar.py` — mensagens WhatsApp (boas compras primeiro)
- `config.json` — regras e procuras do utilizador (a página grava aqui via API do GitHub)
- `docs/regras.json` — descrições, propostas e modelos por tipo
- `docs/index.html` — página (Boas compras, A rever, Procuras, Regras)
- `docs/dados.json`, `estado/vistos.json` — gerados pelo bot
- `.github/workflows/cacador.yml` — agendamento e gravação do estado

Comandos: `python -m cacador.main --teste` (não envia nem grava),
`python -m cacador.main --testar-whatsapp`, `python -m cacador.localidades`.

## Estado

Todo o código foi testado **só com dados simulados** (o ambiente anterior não
tinha internet). Nunca correu contra os sites reais.

Numa leitura manual feita antes, confirmou-se:
- O OLX bloqueou leituras feitas por ferramentas de pesquisa (deteção de bots).
  O endpoint `/api/v1/offers/` ainda não foi testado a partir de um PC normal.
- O CustoJusto deixa ler. Estrutura observada: cada anúncio tem título num link
  (`/distrito/veiculos/motos/moto-4-quad/titulo-45373278`, id no fim), e **o
  preço, o ano e a localidade estão fora do link**, em elementos irmãos. O leitor
  HTML de reserva atual procura o preço dentro do link, por isso tem de ser
  corrigido. Existem páginas por distrito e categoria, por exemplo
  `https://www.custojusto.pt/leiria/veiculos/motos/moto-4-quad`.

## Tarefas seguintes (por esta ordem)

1. Instalar dependências (`pip install -r requirements.txt`) e correr
   `python -m cacador.main --teste`. Ver quantos anúncios lê de cada site.
2. Corrigir o leitor do CustoJusto (preço/local fora do link; confirmar se o
   `__NEXT_DATA__` tem os anúncios). Usar `DEBUG_HTML=1` para guardar a página.
3. Se o OLX bloquear, investigar alternativas (cabeçalhos, ritmo, outro endpoint)
   sem violar os termos do site; se não houver forma, avisar o utilizador.
4. Gerar `docs/localidades.json` com `python -m cacador.localidades` e testar a
   escolha de zonas na página (abrir `docs/index.html` com um servidor local).
5. Ajudar a criar o repositório `cacador-oportunidades` no GitHub da conta do
   utilizador, fazer o push, configurar os Secrets `CALLMEBOT_PHONE` e
   `CALLMEBOT_APIKEY`, ativar o GitHub Pages (branch `main`, pasta `/docs`) e
   correr o workflow à mão.
6. Mais tarde, se o utilizador quiser: Standvirtual (carros) e Imovirtual (casas).

## Cuidados

- Nunca pôr o número de telefone, a apikey do CallMeBot ou tokens no repositório:
  só em Secrets do GitHub ou no `.env` (que está no `.gitignore`).
- Com o repositório público, a página e o `config.json` ficam públicos. Não
  escrever dados pessoais do utilizador (morada, localidade) em ficheiros de
  exemplo ou documentação.
- Frequências moderadas nos sites; respeitar os termos de utilização.

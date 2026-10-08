# 🎯 Caçador de Oportunidades

Vigia o OLX e o CustoJusto e avisa por WhatsApp **só quando aparece uma boa
compra** — um anúncio claramente abaixo do preço normal de mercado.

## Como funciona

O bot aprende o **preço normal de mercado** (mediana dos anúncios semelhantes
dos últimos 120 dias) e separa cada anúncio em três categorias:

| Categoria | Quando | O que acontece |
|---|---|---|
| 🟢 Boa compra | Sem problemas e X% abaixo do mercado | WhatsApp primeiro + página |
| 🟠 A rever | Tem um problema razoável ("não pega", "sem documentos"…) mas um desconto grande | Secção à parte no WhatsApp + página |
| ⚪ Descartado | Problema grave, preço suspeito, acima do orçamento ou preço normal | Nada |

Também avisa quando um anúncio baixa de preço e passa a compensar. Nunca
repete o mesmo alerta.

## Várias procuras ao mesmo tempo

Cada procura tem um tipo, e cada tipo traz propostas próprias:

| Tipo | Compara por | Exemplos de problemas "a rever" |
|---|---|---|
| Mota ou moto4 | preço total, por cilindrada | sem inspeção, IUC em atraso |
| Carro | preço total, por versão | embraiagem, junta da cabeça, salvado |
| Casa | preço por m², por tipologia | para recuperar, em partilhas |
| Terreno | preço por m² (hectares convertidos) | sem acesso, reserva ecológica |
| Outra coisa | preço total | à tua escolha |

Nas casas e terrenos, os anúncios sem área indicada ficam de fora.

## Zonas

Em cada procura escolhes **onde procurar**:

- **Todo o país**
- **Perto de mim:** escolhes a tua terra da lista e um raio (5, 10, 25, 50 km ou
  outro valor). O bot mede a distância real até cada anúncio.
- **Concelhos:** escolhes concelhos ou distritos inteiros da lista.

Os locais escolhem-se de uma lista (sem escrever à mão), por isso não há erros.
A lista vem da base pública GeoNames (geonames.org, licença CC-BY 4.0) e é
descarregada automaticamente na primeira execução para `docs/localidades.json`.
Até lá, a página avisa que a lista ainda não existe.

Para localizar cada anúncio, o bot usa as coordenadas do OLX quando existem, ou
o nome da localidade indicado no anúncio. Anúncios cuja localização não se
consegue confirmar ficam de fora das procuras com zona. Com zona definida, o bot
lê 3 páginas do OLX em vez de 1, para não perder anúncios locais.

## Página: listagem e regras

`docs/index.html` é uma página para o telemóvel com quatro separadores:
**Boas compras**, **A rever**, **Procuras** (criar e editar procuras, com o preço
normal de cada uma) e **Regras** (percentagens e palavras-sinal gerais). Cada regra tem descrição e uma
proposta com botão "Usar proposta".

As regras ficam em `config.json`. As descrições e propostas estão em
`docs/regras.json`: se faltar alguma regra no `config.json`, o bot usa a proposta.

**Ativar a página:** no repositório, Settings → Pages → "Deploy from a branch" →
branch `main`, pasta `/docs` → Save. Fica em
`https://<o-teu-utilizador>.github.io/cacador-oportunidades/`.

**Para guardar regras pela página** é preciso um token (só uma vez, fica guardado
no telemóvel): GitHub → Settings → Developer settings → Fine-grained tokens →
Generate new token → Repository access: só este repositório → Permissions:
Contents "Read and write". Cola-o em Regras → Ligação ao GitHub.

## 1. Ativar o CallMeBot (uma vez)

1. Abre https://www.callmebot.com/blog/free-api-whatsapp-messages/
2. Adiciona aos contactos o número indicado nessa página.
3. Envia-lhe pelo WhatsApp a frase indicada na página.
4. Recebes de volta a tua **apikey**.

## 2. Pôr a correr no GitHub

1. Cria um repositório novo com o nome `cacador-oportunidades` e envia estes ficheiros.
   - **Público** = minutos de Actions ilimitados. Os teus dados privados ficam
     nos Secrets, só as procuras ficam visíveis.
   - **Privado** = 2000 min/mês grátis: muda o cron para `*/30` para caber.
2. Em **Settings → Secrets and variables → Actions → New repository secret**:
   - `CALLMEBOT_PHONE` → o teu número com indicativo, sem "+" (ex.: `351912345678`)
   - `CALLMEBOT_APIKEY` → a apikey do CallMeBot
3. Em **Actions**, ativa os workflows e carrega em **Run workflow** para testar.
4. Vê o registo da execução: deve mostrar quantos anúncios leu por site.

Notas:
- O GitHub pode atrasar execuções agendadas alguns minutos.
- Se o repositório ficar 60 dias sem atividade, o GitHub desliga o agendamento
  (basta reativar no separador Actions).
- Os servidores do GitHub são de datacenter e alguns sites bloqueiam esses
  endereços (erro 403). Se isso acontecer, usa o Raspberry (abaixo).

## 3. Alternativa: Raspberry Pi / PC

```bash
git clone https://github.com/<o-teu-utilizador>/cacador-oportunidades.git
cd cacador-oportunidades
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.exemplo .env        # e preenche o número e a apikey
./venv/bin/python -m cacador.main --testar-whatsapp
./venv/bin/python -m cacador.main --teste
```

Agendar de 15 em 15 min (`crontab -e`):

```
*/15 * * * * cd /home/pi/cacador-oportunidades && ./venv/bin/python -m cacador.main >> cacador.log 2>&1
```

No Raspberry, desativa o workflow do GitHub para não receberes alertas a dobrar.

## Comandos úteis

| Comando | Para quê |
|---|---|
| `python -m cacador.main --teste` | Mostra no ecrã o que enviaria, sem enviar nem gravar |
| `python -m cacador.main --testar-whatsapp` | Confirma que o WhatsApp funciona |
| `DEBUG_HTML=1 python -m cacador.main --teste` | Guarda a página do CustoJusto em `debug/` para diagnóstico |

## Se um site deixar de funcionar

Os sites mudam o seu código de vez em quando. Cada fonte está isolada em
`cacador/fontes/` — se uma falhar, as outras continuam, e o erro aparece no
registo. Para acrescentar fontes (Standvirtual, Facebook Marketplace…), cria um
ficheiro novo com `procurar(sessao, procura)` e regista-o em
`cacador/fontes/__init__.py`.

Usa frequências moderadas e respeita os termos de utilização de cada site.

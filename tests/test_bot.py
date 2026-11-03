import json
import unittest
from pathlib import Path

from bot import analise as A
from bot import avisos, cacador
from bot.fontes import custojusto, olx
from bot.texto import area_do_texto, encontrar, normalizar, numero
from bot.zonas import Localidades, dentro_da_zona

RAIZ = Path(__file__).resolve().parent.parent
REGRAS = json.loads((RAIZ / "docs" / "regras.json").read_text(encoding="utf-8"))
LOC = Localidades({
    "distritos": ["Castelo Branco", "Santarém"],
    "concelhos": [["Penela", 0], ["Alvaiázere", 1]],
    "lugares": [["Penela", 39.801, -8.1, 0, 5000, 3], ["Ansião", 39.79, -8.188, 0, 3000, 1],
                ["Alvaiázere", 39.694, -8.29, 1, 2500, 3]],
})


class Texto(unittest.TestCase):
    def test_acentos_e_prefixo(self):
        t = normalizar("Moto4 AVARIADA, emigração!")
        self.assertEqual(encontrar(t, ["avariad", "emigracao", "urgente"]), ["avariad", "emigracao"])

    def test_grupo_palavra_inteira(self):
        t = normalizar("Suzuki 2500 km")
        self.assertEqual(encontrar(t, ["250"], inteira=True), [])
        self.assertEqual(encontrar(normalizar("Suzuki LT-F 250"), ["250"], inteira=True), ["250"])

    def test_numeros_e_areas(self):
        self.assertEqual(numero("2.450 €"), 2450)
        self.assertEqual(numero("1.234,50"), 1234.5)
        self.assertEqual(area_do_texto("Moradia T3, 190 m²"), 190)
        self.assertEqual(area_do_texto("Terreno com 2 ha"), 20000)


class Zonas(unittest.TestCase):
    def test_raio(self):
        local = LOC.resolver("Ansião")
        ok, km = dentro_da_zona({"modo": "raio", "km": 25, "centro": {"lat": 39.801, "lon": -8.1}}, local)
        self.assertTrue(ok)
        self.assertLess(km, 10)
        ok, _ = dentro_da_zona({"modo": "raio", "km": 5, "centro": {"lat": 39.801, "lon": -8.1}}, LOC.resolver("Alvaiázere"))
        self.assertFalse(ok)

    def test_lista_e_desconhecido(self):
        z = {"modo": "lista", "locais": [{"tipo": "concelho", "nome": "Penela", "distrito": "Castelo Branco"}]}
        self.assertTrue(dentro_da_zona(z, LOC.resolver("Ansião"))[0])
        self.assertFalse(dentro_da_zona(z, LOC.resolver("Alvaiazere"))[0])
        self.assertFalse(dentro_da_zona(z, LOC.resolver("Lugar Inventado"))[0])
        self.assertTrue(dentro_da_zona({"modo": "pais"}, None)[0])


def anuncio(i, titulo, preco, cidade="Penela", desc=""):
    return {"id": f"t-{i}", "fonte": "OLX", "titulo": titulo, "descricao": desc, "preco": preco,
            "area": None, "url": f"https://exemplo.pt/{i}", "cidade": cidade, "distrito": None, "lat": None, "lon": None}


class Fluxo(unittest.TestCase):
    def setUp(self):
        self.p = {"id": "p1", "nome": "Quad", "tipo": "mota", "pesquisa": "quad", "incluir": ["suzuki"],
                  "excluir": ["capacete"], "grupos": ["250", "700"], "comparar_por": "preco",
                  "zona": {"modo": "pais"}, "preco_max": 6000}
        self.config = {"geral": {}, "sinais": {}, "procuras": [self.p]}

    def correr(self, lista, dados=None, estado=None, agora=1_800_000_000):
        dados = dados if dados is not None else {}
        estado = estado if estado is not None else {}
        boas, rever = cacador.processar(self.config, REGRAS, dados, estado, LOC, {"p1": lista}, agora)
        return dados, estado, boas, rever

    def test_classificacao(self):
        mercado = [anuncio(i, f"Suzuki 250 quad {i}", 3000 + i * 10) for i in range(8)]
        extra = [
            anuncio("boa", "Suzuki 250 baratinha", 2400),                               # −20%
            anuncio("pressa", "Suzuki 250 urgente", 2650),                              # −12%, com folga de 5
            anuncio("fraca", "Suzuki 250 ok", 2900),                                    # −4%
            anuncio("burla", "Suzuki 250 quase oferta", 1000),                          # < 50% do mercado
            anuncio("rever", "Suzuki 250 não pega", 1700),                              # problema, −44%
            anuncio("grave", "Suzuki 250 penhora", 1500),                               # descartado
            anuncio("excl", "Capacete Suzuki", 50),                                     # excluído
            anuncio("caro", "Suzuki 250 nova", 7000),                                   # acima do orçamento
            anuncio("700", "Suzuki 700 barata", 2000),                                  # grupo sem amostras
        ]
        dados, estado, boas, rever = self.correr(mercado + extra)
        cat = {i: a["categoria"] for i, a in dados["anuncios"].items()}
        self.assertEqual(cat, {"t-boa": "boa", "t-pressa": "boa", "t-rever": "rever"})
        self.assertEqual({a["titulo"] for a in boas}, {"Suzuki 250 baratinha", "Suzuki 250 urgente"})
        self.assertEqual(len(rever), 1)
        self.assertIn("250", dados["mercado"]["Quad"])
        self.assertNotIn("t-caro", dados["anuncios"])

        # Segunda verificação: não repete alertas; baixa de preço volta a avisar.
        lista2 = mercado + [anuncio("boa", "Suzuki 250 baratinha", 2400), anuncio("pressa", "Suzuki 250 urgente", 2500)]
        dados, estado, boas, rever = self.correr(lista2, dados, estado, 1_800_000_900)
        self.assertEqual([a["titulo"] for a in boas], ["Suzuki 250 urgente"])
        self.assertEqual(dados["anuncios"]["t-pressa"]["preco_antes"], 2650)

        # Procura pausada: os anúncios saem da página.
        self.p["ativa"] = False
        dados, *_ = self.correr([], dados, estado, 1_800_001_800)
        self.assertEqual(dados["anuncios"], {})

    def test_mensagem(self):
        a = {"tipo": "mota", "procura": "Quad", "titulo": "Suzuki <LT-F> & guincho", "preco": 2450, "desconto": 0.216,
             "mediana": 3125, "unidade": "€", "preco_antes": None, "problemas": [], "sinais": ["urgente"],
             "local": "Penela", "km": 4, "fonte": "OLX", "url": "https://x/?a=1&b=2"}
        m = avisos.montar_mensagens([a], [], "whatsapp")
        self.assertEqual(len(m), 1)
        self.assertIn("2 450 €", m[0])
        self.assertIn("−22%", m[0])
        t = avisos.montar_mensagens([a], [], "telegram")[0]
        self.assertIn("<b>Suzuki &lt;LT-F&gt; &amp; guincho</b>", t)  # HTML do Telegram escapado
        self.assertIn('<a href="https://x/?a=1&amp;b=2">', t)

    def test_mensagens_divididas(self):
        a = {"tipo": "mota", "procura": "Q", "titulo": "x" * 300, "preco": 1, "desconto": 0.5, "mediana": 2,
             "unidade": "€", "problemas": [], "sinais": [], "local": "", "km": None, "fonte": "OLX", "url": ""}
        m = avisos.montar_mensagens([a] * 20, [], "telegram", limite=3800)
        self.assertGreater(len(m), 1)
        self.assertTrue(all(len(x) <= 3800 for x in m))


class Fontes(unittest.TestCase):
    def test_olx(self):
        o = {"id": 9, "title": "Moradia T3 190 m²", "description": "<p>Boa</p>", "url": "https://www.olx.pt/d/x",
             "params": [{"key": "price", "value": {"value": 139000, "type": "price"}}],
             "location": {"city": {"name": "Penela"}, "region": {"name": "Castelo Branco"}}, "map": {"lat": 39.8, "lon": -8.1}}
        a = olx.converter(o)
        self.assertEqual((a["id"], a["preco"], a["area"], a["cidade"]), ("olx-9", 139000, 190, "Penela"))

    def test_custojusto(self):
        nd = {"props": {"pageProps": {"listItems": [
            {"listID": 1, "title": "Clio 1.5 dCi", "price": "6.900 €", "url": "/tomar/carros/clio-1", "municipality": "Tomar"},
            {"listID": 2, "title": "Clio 0.9", "price": 5500, "url": "https://www.custojusto.pt/x", "location": {"region": "Santarém"}},
            # Formato real observado em 2026-11:
            {"listID": "3", "title": "Moradia", "price": 125000, "params": {"size": "1.260m²"},
             "url": "https://www.custojusto.pt/castelo-branco/imobiliario/moradias/x-3",
             "locationNames": {"county": "Penela", "parish": "Ansião"}},
        ]}}}
        html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script></html>'
        r = custojusto.extrair(html)
        self.assertEqual([a["preco"] for a in r], [6900, 5500, 125000])
        self.assertTrue(r[0]["url"].startswith("https://www.custojusto.pt/tomar"))
        self.assertEqual(r[1]["distrito"], "Santarém")
        self.assertEqual((r[2]["cidade"], r[2]["distrito"], r[2]["area"]), ("Penela", "castelo branco", 1260))
        local = LOC.resolver(r[2]["cidade"], r[2]["distrito"])
        self.assertEqual(local["concelho"], "Penela")


if __name__ == "__main__":
    unittest.main()

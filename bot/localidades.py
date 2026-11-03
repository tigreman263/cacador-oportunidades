"""Cria docs/localidades.json a partir do GeoNames (CC BY 4.0, https://www.geonames.org).

Formato (o que a página espera):
  distritos: ["Aveiro", ...]
  concelhos: [[nome, índice_distrito], ...]
  lugares:   [[nome, lat, lon, índice_concelho, população, prioridade], ...]
Prioridade: 4 capital de distrito, 3 sede de concelho, 2 sede de freguesia, 1 outros.
"""
import io
import json
import zipfile

BASE = "https://download.geonames.org/export/dump/"
RENOMEAR = {"Azores": "Açores"}
PRIORIDADE = {"PPLC": 4, "PPLA": 4, "PPLA2": 3, "PPLA3": 2}


def _linhas(sessao, ficheiro):
    r = sessao.get(BASE + ficheiro, timeout=120)
    r.raise_for_status()
    return r.content.decode("utf-8").splitlines()


def construir(sessao) -> dict:
    a1 = {}
    for l in _linhas(sessao, "admin1CodesASCII.txt"):
        cod, nome, *_ = l.split("\t")
        if cod.startswith("PT."):
            a1[cod.split(".")[1]] = RENOMEAR.get(nome, nome)
    a2 = {}
    for l in _linhas(sessao, "admin2Codes.txt"):
        cod, nome, *_ = l.split("\t")
        if cod.startswith("PT."):
            _, c1, c2 = cod.split(".")
            if c1 in a1:
                a2[(c1, c2)] = nome

    r = sessao.get(BASE + "PT.zip", timeout=180)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        texto = z.read("PT.txt").decode("utf-8")

    distritos = sorted(set(a1.values()))
    d_idx = {n: i for i, n in enumerate(distritos)}
    conc_lista = sorted({(nome, a1[c1]) for (c1, _), nome in a2.items()})
    c_idx = {c: i for i, c in enumerate(conc_lista)}
    concelhos = [[n, d_idx[d]] for n, d in conc_lista]

    lugares = []
    for l in texto.splitlines():
        c = l.split("\t")
        if len(c) < 15 or c[6] != "P":
            continue
        k = (c[10], c[11])
        if k not in a2:
            continue
        ci = c_idx[(a2[k], a1[c[10]])]
        lugares.append([c[1], round(float(c[4]), 3), round(float(c[5]), 3), ci,
                        int(c[14] or 0), PRIORIDADE.get(c[7], 1)])
    lugares.sort(key=lambda x: (-x[5], -x[4], x[0]))
    return {"fonte": "geonames", "distritos": distritos, "concelhos": concelhos, "lugares": lugares}


def gravar(caminho, sessao):
    d = construir(sessao)
    caminho.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return d

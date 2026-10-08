"""Localidades de Portugal com coordenadas (base pública GeoNames, CC-BY).

- `python -m cacador.localidades` descarrega a base e cria docs/localidades.json
  (usado pela página para escolher zonas e pelo bot para medir distâncias).
- `Localizador` descobre onde fica um anúncio e mede distâncias.
"""
import io
import json
import math
import zipfile
from pathlib import Path

import requests

from .modelo import normalizar

RAIZ = Path(__file__).resolve().parent.parent
FICHEIRO = RAIZ / "docs" / "localidades.json"

URL_PAIS = "https://download.geonames.org/export/dump/PT.zip"
URL_ADMIN1 = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
URL_ADMIN2 = "https://download.geonames.org/export/dump/admin2Codes.txt"

# lugares povoados; ficam de fora os históricos, abandonados e destruídos
CODIGOS_FORA = {"PPLH", "PPLQ", "PPLW", "PPLCH"}
PRIORIDADE = {"PPLC": 5, "PPLA": 4, "PPLA2": 3, "PPLA3": 2, "PPL": 1}


def _codigos(texto, prefixo):
    saida = {}
    for linha in texto.splitlines():
        partes = linha.split("\t")
        if len(partes) >= 2 and partes[0].startswith(prefixo):
            saida[partes[0]] = partes[1]
    return saida


def construir_de_texto(pt_txt, admin1_txt, admin2_txt):
    """Converte os ficheiros GeoNames no formato compacto usado aqui."""
    distritos_cod = _codigos(admin1_txt, "PT.")
    concelhos_cod = _codigos(admin2_txt, "PT.")

    distritos, concelhos = [], []
    idx_d, idx_c = {}, {}
    lugares = []
    for linha in pt_txt.splitlines():
        p = linha.split("\t")
        if len(p) < 15 or p[6] != "P" or p[7] in CODIGOS_FORA:
            continue
        d_nome = distritos_cod.get(f"PT.{p[10]}")
        c_nome = concelhos_cod.get(f"PT.{p[10]}.{p[11]}")
        if not d_nome or not c_nome:
            continue
        if d_nome not in idx_d:
            idx_d[d_nome] = len(distritos)
            distritos.append(d_nome)
        chave_c = (c_nome, idx_d[d_nome])
        if chave_c not in idx_c:
            idx_c[chave_c] = len(concelhos)
            concelhos.append([c_nome, idx_d[d_nome]])
        lugares.append([
            p[1], round(float(p[4]), 4), round(float(p[5]), 4),
            idx_c[chave_c], int(p[14] or 0), PRIORIDADE.get(p[7], 0),
        ])
    return {"fonte": "GeoNames (geonames.org), CC-BY 4.0",
            "distritos": distritos, "concelhos": concelhos, "lugares": lugares}


def construir():
    print("A descarregar localidades de Portugal (GeoNames)…")
    z = zipfile.ZipFile(io.BytesIO(requests.get(URL_PAIS, timeout=120).content))
    pt_txt = z.read("PT.txt").decode("utf-8")
    admin1 = requests.get(URL_ADMIN1, timeout=120).text
    admin2 = requests.get(URL_ADMIN2, timeout=120).text
    dados = construir_de_texto(pt_txt, admin1, admin2)
    FICHEIRO.parent.mkdir(exist_ok=True)
    FICHEIRO.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(dados['lugares'])} localidades, {len(dados['concelhos'])} concelhos gravados.")
    return dados


def distancia_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df, dl = f2 - f1, math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Localizador:
    def __init__(self, dados):
        self.distritos = dados["distritos"]
        self.concelhos = dados["concelhos"]
        self.lugares = dados["lugares"]
        self.por_nome = {}
        for i, l in enumerate(self.lugares):
            self.por_nome.setdefault(normalizar(l[0]), []).append(i)
        self.concelho_por_nome = {}
        for i, (nome, _d) in enumerate(self.concelhos):
            self.concelho_por_nome.setdefault(normalizar(nome), []).append(i)
        self.distrito_por_nome = {normalizar(n): i for i, n in enumerate(self.distritos)}

    @classmethod
    def carregar(cls, construir_se_faltar=True):
        if not FICHEIRO.exists():
            if not construir_se_faltar:
                return None
            try:
                construir()
            except Exception as erro:
                print(f"[aviso] não foi possível descarregar localidades: {erro}")
                return None
        return cls(json.loads(FICHEIRO.read_text(encoding="utf-8")))

    def _info(self, i):
        nome, lat, lon, c, _pop, _pri = self.lugares[i]
        return {"lat": lat, "lon": lon, "concelho": self.concelhos[c][0],
                "distrito": self.distritos[self.concelhos[c][1]], "lugar": nome}

    def _melhor(self, indices):
        return max(indices, key=lambda i: (self.lugares[i][5], self.lugares[i][4]))

    def localizar(self, texto):
        """ "Sertã, Castelo Branco" -> {lat, lon, concelho, distrito}. None se não souber."""
        partes = [normalizar(p) for p in (texto or "").replace("-", ",").split(",") if p.strip()]
        if not partes:
            return None
        concelhos_ditos = {c for p in partes for c in self.concelho_por_nome.get(p, [])}
        distritos_ditos = {self.distrito_por_nome[p] for p in partes if p in self.distrito_por_nome}

        for p in partes:
            candidatos = self.por_nome.get(p, [])
            if not candidatos:
                continue
            filtrados = [i for i in candidatos
                         if (not concelhos_ditos or self.lugares[i][3] in concelhos_ditos or
                             normalizar(self.concelhos[self.lugares[i][3]][0]) == p)
                         and (not distritos_ditos or self.concelhos[self.lugares[i][3]][1] in distritos_ditos)]
            return self._info(self._melhor(filtrados or candidatos))

        # só o nome do concelho: usa a maior localidade desse concelho
        for p in partes:
            for c in self.concelho_por_nome.get(p, []):
                dentro = [i for i, l in enumerate(self.lugares) if l[3] == c]
                if dentro:
                    return self._info(self._melhor(dentro))
        return None

    def mais_proximo(self, lat, lon):
        """Concelho e distrito de um ponto (para anúncios com coordenadas)."""
        i = min(range(len(self.lugares)),
                key=lambda k: (self.lugares[k][1] - lat) ** 2 + (self.lugares[k][2] - lon) ** 2)
        info = self._info(i)
        info.update(lat=lat, lon=lon)
        return info


def dentro_da_zona(onde, zona):
    """onde: {lat, lon, concelho, distrito} ou None. zona: config da procura."""
    modo = (zona or {}).get("modo", "pais")
    if modo == "pais":
        return True
    if onde is None:
        return False  # não se sabe onde fica: não arrisca
    if modo == "raio":
        c = zona.get("centro") or {}
        if "lat" not in c:
            return True
        return distancia_km(c["lat"], c["lon"], onde["lat"], onde["lon"]) <= float(zona.get("km") or 10)
    if modo == "lista":
        for l in zona.get("locais") or []:
            if l.get("tipo") == "distrito" and normalizar(l["nome"]) == normalizar(onde["distrito"]):
                return True
            if (l.get("tipo") == "concelho" and normalizar(l["nome"]) == normalizar(onde["concelho"])
                    and (not l.get("distrito") or normalizar(l["distrito"]) == normalizar(onde["distrito"]))):
                return True
        return False
    return True


if __name__ == "__main__":
    construir()

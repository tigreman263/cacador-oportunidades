"""Localização dos anúncios e filtro "Onde procurar" (país, raio em km, lista de concelhos/distritos)."""
import math
from collections import defaultdict

from .texto import sem_acento


def distancia_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Localidades:
    """Lê o docs/localidades.json (o mesmo que a página usa para escolher locais)."""

    def __init__(self, d: dict):
        self.lugares = []
        self.por_nome = defaultdict(list)
        self.concelho_distrito = {}
        for nome, di in d.get("concelhos", []):
            self.concelho_distrito[sem_acento(nome)] = d["distritos"][di]
        for nome, lat, lon, c, pop, pri in d.get("lugares", []):
            cnome, di = d["concelhos"][c]
            x = {"nome": nome, "lat": lat, "lon": lon, "concelho": cnome,
                 "distrito": d["distritos"][di], "pop": pop or 0, "pri": pri or 0}
            self.lugares.append(x)
            self.por_nome[sem_acento(nome)].append(x)

    def mais_proximo(self, lat, lon):
        return min(self.lugares, key=lambda x: (x["lat"] - lat) ** 2 + ((x["lon"] - lon) * 0.77) ** 2, default=None)

    def resolver(self, cidade=None, distrito=None, lat=None, lon=None):
        """Devolve {nome, lat, lon, concelho, distrito} ou None se não se conseguir confirmar."""
        cands = list(self.por_nome.get(sem_acento(cidade), [])) if cidade else []
        # A cidade pode ser o próprio concelho (ex.: "Sertã").
        if not cands and cidade and sem_acento(cidade) in self.concelho_distrito:
            cands = [x for x in self.lugares if sem_acento(x["concelho"]) == sem_acento(cidade)]
        if distrito and cands:
            no_distrito = [x for x in cands if sem_acento(x["distrito"]) == sem_acento(distrito)]
            cands = no_distrito or cands
        temos_coord = lat is not None and lon is not None
        if cands:
            if temos_coord:
                melhor = min(cands, key=lambda x: distancia_km(lat, lon, x["lat"], x["lon"]))
            else:
                melhor = max(cands, key=lambda x: (x["pri"], x["pop"]))
            res = dict(melhor)
        elif temos_coord:
            perto = self.mais_proximo(lat, lon)
            if not perto or distancia_km(lat, lon, perto["lat"], perto["lon"]) > 15:
                return {"nome": cidade, "lat": lat, "lon": lon, "concelho": None, "distrito": distrito}
            res = dict(perto)
        else:
            return None
        if temos_coord:
            res["lat"], res["lon"] = lat, lon
        if cidade:
            res["nome"] = cidade
        return res


def dentro_da_zona(zona, local):
    """Devolve (aceite, km). Anúncios cuja localização não se confirma ficam de fora (exceto 'Todo o país')."""
    zona = zona or {}
    modo = zona.get("modo") or "pais"
    if modo == "pais":
        return True, None
    if not local:
        return False, None
    if modo == "raio":
        c = zona.get("centro")
        if not c or local.get("lat") is None:
            return False, None
        km = distancia_km(c["lat"], c["lon"], local["lat"], local["lon"])
        return km <= float(zona.get("km") or 10), round(km)
    if modo == "lista":
        conc, dist = sem_acento(local.get("concelho")), sem_acento(local.get("distrito"))
        for l in zona.get("locais") or []:
            if l.get("tipo") == "distrito" and dist and sem_acento(l["nome"]) == dist:
                return True, None
            if l.get("tipo") == "concelho" and conc and sem_acento(l["nome"]) == conc:
                if not l.get("distrito") or not dist or sem_acento(l["distrito"]) == dist:
                    return True, None
        return False, None
    return True, None

"""CustoJusto. O site é uma app Next.js: os anúncios vêm no JSON do <script id="__NEXT_DATA__">.

A estrutura interna desse JSON não é pública e pode mudar, por isso a extração é "defensiva":
procura no JSON listas de objetos que pareçam anúncios (têm título, preço e id/url).
Se o site mudar e nada for encontrado, o bot regista um aviso e continua com as outras fontes.
"""
import json
import logging
import time
import re
from urllib.parse import quote

from ..texto import area_do_texto, numero

BASE = "https://www.custojusto.pt"
log = logging.getLogger(__name__)

K_TITULO = ("title", "subject", "titulo")
K_PRECO = ("price", "preco", "priceValue")
K_ID = ("listID", "listId", "id", "adId")
K_URL = ("url", "link", "href", "permalink")


def _primeiro(o, chaves):
    for k in chaves:
        if o.get(k) not in (None, ""):
            return o[k]
    return None


def _parece_anuncio(o) -> bool:
    return bool(isinstance(o, dict) and _primeiro(o, K_TITULO) and _primeiro(o, K_ID) is not None
                and any(k in o for k in K_PRECO))


def _anuncios_no_json(no, achados):
    if isinstance(no, list):
        if no and sum(_parece_anuncio(x) for x in no) >= max(1, len(no) // 2):
            achados.extend(x for x in no if _parece_anuncio(x))
            return
        for x in no:
            _anuncios_no_json(x, achados)
    elif isinstance(no, dict):
        for v in no.values():
            _anuncios_no_json(v, achados)


def _texto_local(v):
    if isinstance(v, dict):
        return _primeiro(v, ("name", "label", "nome", "value"))
    return v


def converter(o: dict) -> dict:
    preco = _primeiro(o, K_PRECO)
    if isinstance(preco, dict):
        preco = _primeiro(preco, ("value", "amount", "label"))
    url = _primeiro(o, K_URL) or ""
    if url and not url.startswith("http"):
        url = BASE + ("" if url.startswith("/") else "/") + url
    titulo = str(_primeiro(o, K_TITULO)).strip()
    descricao = str(_primeiro(o, ("body", "description", "descricao")) or "")
    local = o.get("location") if isinstance(o.get("location"), dict) else {}
    nomes = o.get("locationNames") if isinstance(o.get("locationNames"), dict) else {}  # {"county": concelho, "parish": freguesia}
    params = o.get("params") if isinstance(o.get("params"), dict) else {}
    cidade = _texto_local(nomes.get("county") or _primeiro(o, ("municipality", "city", "concelho", "locationName"))
                          or _primeiro(local, ("municipality", "city", "name")))
    distrito = _texto_local(_primeiro(o, ("region", "district", "distrito")) or _primeiro(local, ("region", "district")))
    categoria = None
    if url.startswith(BASE + "/"):
        # https://www.custojusto.pt/<distrito>/<categoria>/<subcategoria>/.../<anuncio>
        segs = url[len(BASE) + 1:].split("?")[0].split("/")
        if not distrito and segs[0] and segs[0] != "portugal":
            distrito = segs[0].replace("-", " ")
        categoria = " ".join(s.replace("-", " ") for s in segs[1:-1]) or None
    return {
        "id": f"cj-{_primeiro(o, K_ID)}",
        "fonte": "CustoJusto",
        "titulo": titulo,
        "descricao": descricao,
        "preco": numero(preco),
        "area": numero(_primeiro(params, ("size", "area")) or _primeiro(o, ("size", "area", "m2")))
                or area_do_texto(titulo) or area_do_texto(descricao),
        "url": url or None,
        "categoria": categoria,  # ex.: "veiculos pecas acessorios pecas acessorios carro"
        "cidade": cidade,
        "distrito": distrito,
        "lat": numero(_primeiro(local, ("lat", "latitude"))),
        "lon": numero(_primeiro(local, ("lon", "lng", "longitude"))),
    }


def extrair(html: str) -> list:
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    achados = []
    _anuncios_no_json(json.loads(m.group(1)), achados)
    vistos, res = set(), []
    for o in achados:
        a = converter(o)
        if a["id"] not in vistos:
            vistos.add(a["id"])
            res.append(a)
    return res


def endereco(pesquisa: str, categoria: str = "", pagina: int = 1) -> str:
    """Pesquisa no país todo; com categoria (ex.: "veiculos/motos/moto-4-quad") só procura lá dentro."""
    cat = (categoria or "").strip("/ ")
    caminho = f"/portugal/{cat}" if cat else "/portugal"
    if pesquisa.strip():
        caminho += f"/q/{quote(pesquisa.strip())}"
    return BASE + caminho + (f"?o={pagina}" if pagina > 1 else "")


def da_categoria(a: dict, categoria: str) -> bool:
    """True se o anúncio é da categoria pedida (ex.: "veiculos/motos/moto-4-quad"), ou se não há categoria."""
    cat = (categoria or "").strip("/ ").replace("/", " ").replace("-", " ")
    return not cat or not a.get("categoria") or (a["categoria"] + " ").startswith(cat + " ")


def procurar(sessao, pesquisa: str, paginas: int = 2, categoria: str = "", pausa: float = 2.0):
    vistos = set()
    for pagina in range(1, paginas + 1):
        if pagina > 1:
            time.sleep(pausa)
        r = sessao.get(endereco(pesquisa, categoria, pagina), timeout=30)
        if r.status_code != 200:
            log.warning("CustoJusto respondeu %s para '%s' (página %d)", r.status_code, pesquisa, pagina)
            return
        todos = [a for a in extrair(r.text) if a["id"] not in vistos]
        # Com poucos resultados, o site enche a página com "destaques" de outras categorias
        # (carros numa procura de motos 4). Esses ficam de fora.
        novos = [a for a in todos if da_categoria(a, categoria)]
        if not todos:
            if pagina == 1:
                log.warning("CustoJusto: nenhum anúncio reconhecido em '%s' (o site pode ter mudado)", pesquisa)
            return
        vistos.update(a["id"] for a in todos)
        yield from novos
        if not novos:
            return  # a página já só tinha destaques: as seguintes também

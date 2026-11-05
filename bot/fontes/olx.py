"""OLX Portugal, através da API pública que o próprio site usa nas listagens."""
import logging
import re

from ..texto import area_do_texto, numero

API = "https://www.olx.pt/api/v1/offers/"
SITE = "https://www.olx.pt"


def endereco_pesquisa(p: dict) -> str:
    """Link da pesquisa no site do OLX com o texto e o orçamento da procura, para o utilizador
    abrir no seu navegador (botão "Abrir no OLX"). O bot não visita este endereço."""
    from ..texto import normalizar
    termo = "-".join(re.sub(r"[^a-z0-9]+", " ", normalizar(p.get("pesquisa") or "")).split())
    if not termo:
        return ""
    url = f"{SITE}/ads/q-{termo}/"
    if p.get("preco_max"):
        url += f"?search%5Bfilter_float_price%3Ato%5D={int(p['preco_max'])}"
    return url
CHAVES_AREA = {"m", "area", "area_util", "area_bruta", "area_total", "area_de_terreno", "area_terreno"}
log = logging.getLogger(__name__)


def converter(o: dict) -> dict:
    preco = area = None
    for p in o.get("params") or []:
        k, v = p.get("key"), p.get("value") or {}
        if k == "price":
            if v.get("type") in (None, "price", "arranged"):
                preco = numero(v.get("value"))
        elif k in CHAVES_AREA and area is None:
            area = numero(v.get("key") or v.get("label"))
    titulo = o.get("title") or ""
    descricao = re.sub(r"<[^>]+>", " ", o.get("description") or "")
    if area is None:
        area = area_do_texto(titulo) or area_do_texto(descricao)
    loc, mapa = o.get("location") or {}, o.get("map") or {}
    return {
        "id": f"olx-{o.get('id')}",
        "fonte": "OLX",
        "titulo": titulo.strip(),
        "descricao": descricao,
        "preco": preco,
        "area": area,
        "url": o.get("url"),
        "cidade": (loc.get("city") or {}).get("name"),
        "distrito": (loc.get("region") or {}).get("name"),
        "lat": mapa.get("lat"),
        "lon": mapa.get("lon"),
    }


def procurar(sessao, pesquisa: str, paginas: int = 2, por_pagina: int = 40):
    for pag in range(paginas):
        r = sessao.get(API, params={"offset": pag * por_pagina, "limit": por_pagina,
                                    "query": pesquisa, "sort_by": "created_at:desc"}, timeout=30)
        if r.status_code != 200:
            log.warning("OLX respondeu %s para '%s'", r.status_code, pesquisa)
            return
        dados = (r.json() or {}).get("data") or []
        for o in dados:
            try:
                yield converter(o)
            except Exception as e:  # um anúncio estranho não deve parar a verificação
                log.warning("OLX: anúncio ignorado (%s)", e)
        if len(dados) < por_pagina:
            return

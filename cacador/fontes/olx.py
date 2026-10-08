"""OLX Portugal — usa o endpoint JSON que o próprio site usa nas pesquisas."""
from ..modelo import Anuncio, area_do_texto, para_numero

API = "https://www.olx.pt/api/v1/offers/"


def procurar(sessao, procura) -> list[Anuncio]:
    params = {
        "offset": 0,
        "limit": 50,
        "query": procura["pesquisa"],
        "sort_by": "created_at:desc",
    }
    if procura.get("preco_min") is not None:
        params["filter_float_price:from"] = procura["preco_min"]
    if procura.get("preco_max") is not None:
        params["filter_float_price:to"] = procura["preco_max"]

    # com zona pequena lê mais páginas, para não perder anúncios locais
    paginas = 3 if (procura.get("zona") or {}).get("modo", "pais") != "pais" else 1
    itens = []
    for pagina in range(paginas):
        params["offset"] = pagina * 50
        r = sessao.get(API, params=params, timeout=25)
        r.raise_for_status()
        lote = r.json().get("data", [])
        itens += lote
        if len(lote) < 50:
            break

    anuncios = []
    for item in itens:
        preco, area = None, None
        for p in item.get("params", []):
            chave = p.get("key") or ""
            if chave == "price":
                preco = para_numero(p.get("value"))
            elif chave == "m" or "area" in chave:
                area = area or para_numero(p.get("value"))
        mapa = item.get("map") or {}
        loc = item.get("location") or {}
        partes = [(loc.get("city") or {}).get("name"), (loc.get("region") or {}).get("name")]
        anuncios.append(Anuncio(
            fonte="OLX",
            id=f"olx:{item.get('id')}",
            titulo=item.get("title", ""),
            preco=preco,
            local=", ".join(p for p in partes if p),
            url=item.get("url", ""),
            descricao=item.get("description", "") or "",
            area=area,
            lat=mapa.get("lat"),
            lon=mapa.get("lon"),
        ))
    return anuncios

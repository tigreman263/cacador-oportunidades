"""AutoUncle Portugal: carros usados de muitos sites (stands e particulares) num só sítio.

Lê os dados estruturados (schema.org, "application/ld+json") que a página de resultados publica.
Só tem carros. Não pesquisa por texto: escolhe-se o tipo de carro (SUV, carrinha, van…) e o
bot junta o limite de preço; o filtro de palavras da procura faz o resto.
O robots.txt do site permite estas páginas; o bot lê só 2 páginas por procura.
"""
import json
import logging
import re
import time

log = logging.getLogger(__name__)

BASE = "https://www.autouncle.pt/pt/carros-usados"
# Limites de preço que o site tem como página própria ("mp-abaixo-de-3000-euro").
PRECOS = [1000, 3000, 5000, 10000, 15000]
TIPOS = {  # valor guardado na procura -> nome no site
    "b-suv": "SUV / jipe", "b-carrinha-combi": "Carrinha", "b-van": "Van / comercial",
    "b-utilitario": "Utilitário", "b-sedan": "Sedan", "b-monovolume": "Monovolume",
    "b-coupe": "Coupé", "b-cabrios": "Descapotável",
}


def endereco(tipo_carro: str = "", preco_max=None, pagina: int = 1) -> str:
    """Página de resultados. O limite de preço fica acima do orçamento (1,5×), para o bot
    também ver os carros mais caros e calcular bem o preço normal."""
    partes = [BASE]
    if tipo_carro:
        partes.append(tipo_carro.strip("/ "))
    if preco_max:
        teto = next((v for v in PRECOS if v >= float(preco_max) * 1.5), None)
        if teto:
            partes.append(f"mp-abaixo-de-{teto}-euro")
    return "/".join(partes) + (f"?page={pagina}" if pagina > 1 else "")


def converter(item: dict) -> dict:
    oferta = item.get("offers") or {}
    url = (oferta.get("url") or item.get("@id") or "").split("#")[0]
    num = re.search(r"/d/(\d+)", url)
    nome = re.sub(r"^\s*(Usado|Novo)\s*\(\d{4}\)\s*", "", item.get("name") or "").replace(" HP", " cv")
    ano, comb, corpo = item.get("vehicleModelDate"), item.get("fuelType"), item.get("bodyType")
    # O título junta o combustível e o tipo de carro, para os filtros e os grupos da procura
    # (ex.: "diesel", "SUV") funcionarem como nos outros sites.
    titulo = " ".join(str(x) for x in [nome, f"- {ano}" if ano else "", comb or "", corpo or ""] if x).strip()
    km = (item.get("mileageFromOdometer") or {}).get("value")
    extra = [item.get("description") or "", f"{km} km" if km else "", item.get("vehicleTransmission") or ""]
    try:
        preco = float(oferta.get("price"))
    except (TypeError, ValueError):
        preco = None
    return {
        "id": f"autouncle-{num.group(1) if num else url}",
        "fonte": "AutoUncle",
        "titulo": titulo,
        "descricao": " ".join(x for x in extra if x),
        "preco": preco,
        "area": None,
        "url": url,
        "cidade": None, "distrito": None, "lat": None, "lon": None,
    }


def extrair(html: str) -> list:
    m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*id="schema-search-results"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        grafo = json.loads(m.group(1)).get("@graph") or []
    except ValueError:
        return []
    lista = next((x for x in grafo if x.get("@type") == "ItemList"), {}).get("itemListElement") or []
    return [converter(x["item"]) for x in lista if isinstance(x, dict) and isinstance(x.get("item"), dict)]


def procurar(sessao, pesquisa: str, paginas: int = 2, tipo_carro: str = "", preco_max=None, pausa: float = 2.0):
    vistos = set()
    for pagina in range(1, paginas + 1):
        if pagina > 1:
            time.sleep(pausa)
        r = sessao.get(endereco(tipo_carro, preco_max, pagina), timeout=30)
        if r.status_code != 200:
            if pagina == 1:
                log.warning("AutoUncle respondeu %s", r.status_code)
            return
        novos = [a for a in extrair(r.text) if a["id"] not in vistos]
        if not novos:
            if pagina == 1:
                log.warning("AutoUncle: nenhum carro reconhecido (o site pode ter mudado)")
            return
        vistos.update(a["id"] for a in novos)
        yield from novos

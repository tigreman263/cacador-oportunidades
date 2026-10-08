"""Estrutura comum a todas as fontes (OLX, CustoJusto, ...)."""
import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Anuncio:
    fonte: str          # "OLX", "CustoJusto"
    id: str             # único e estável, ex.: "olx:123456"
    titulo: str
    preco: float | None
    local: str
    url: str
    descricao: str = ""
    area: float | None = None   # m², quando o anúncio indica
    lat: float | None = None    # coordenadas, quando o site as dá
    lon: float | None = None


def normalizar(texto: str) -> str:
    """minúsculas, sem acentos, sem hífens/pontos (lt-f -> ltf)."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[-_.]", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def para_numero(valor) -> float | None:
    """Converte 2500, "2 500 €", "2.500,00 €", {"value": 2500} em float."""
    if valor is None:
        return None
    if isinstance(valor, dict):
        for chave in ("value", "amount", "valor", "price", "key", "label"):
            if chave in valor:
                return para_numero(valor[chave])
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor)
    texto = re.sub(r"[^\d,.]", "", texto)
    if not texto:
        return None
    # formato PT: "2.500,50" -> 2500.50 ; "2 500" -> 2500
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif texto.count(".") >= 1 and len(texto.split(".")[-1]) == 3:
        texto = texto.replace(".", "")
    try:
        return float(texto)
    except ValueError:
        return None


def extrair_area(texto: str) -> float | None:
    """Procura "120 m2", "1.500 m²", "2,5 ha", "3 hectares" no texto."""
    t = normalizar(texto)  # "m²" vira "m2"; "1.500" vira "1500"
    m = re.search(r"(\d+(?:,\d+)?)\s?(?:m2|mts2|mt2|metros quadrados)\b", t)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+(?:,\d+)?)\s?(?:ha|hectares?)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 10000
    return None


# nome antigo, mantido por compatibilidade
area_do_texto = extrair_area

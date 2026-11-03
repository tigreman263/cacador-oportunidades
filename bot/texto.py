"""Normalização de texto e procura de palavras-sinal.

Regras (iguais às explicadas na página):
- maiúsculas e acentos não contam;
- uma palavra incompleta apanha as variações ("avariad" apanha avariado/avariada);
- nos "grupos" (cilindrada, tipologia…) a palavra tem de estar inteira ("250" não apanha "2500").
"""
import re
import unicodedata
from functools import lru_cache


def sem_acento(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def normalizar(s) -> str:
    s = re.sub(r"<[^>]+>", " ", str(s or ""))  # descrições do OLX vêm em HTML
    s = sem_acento(s)
    s = re.sub(r"[^a-z0-9.,/+]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=4096)
def _padrao(termo: str, inteira: bool):
    t = normalizar(termo)
    if not t:
        return None
    p = r"(?<![a-z0-9])" + re.escape(t)
    if inteira:
        p += r"(?![a-z0-9])"
    return re.compile(p)


def encontrar(texto_norm: str, termos, inteira: bool = False) -> list:
    """Devolve os termos (como escritos na config) que aparecem no texto já normalizado."""
    achados = []
    for t in termos or []:
        p = _padrao(str(t), inteira)
        if p is not None and p.search(texto_norm):
            achados.append(t)
    return achados


def area_do_texto(s):
    """Tenta ler uma área em m² de um título/descrição: '190 m²', '1.500m2', '2 ha'."""
    t = sem_acento(s)
    # Separador de milhares só com ponto ("1.500"): com espaço, "T3 190 m²" seria lido como 3190.
    m = re.search(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?\s*(?:m2|m²|mts2|metros quadrados)", t)
    if m:
        return float(m.group(1).replace(".", ""))
    m = re.search(r"(\d+(?:,\d+)?)\s*(?:ha|hectares?)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 10000
    return None


def numero(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^\d,.]", "", str(v))
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None

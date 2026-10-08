"""CustoJusto — lê a página de pesquisa.

Tenta primeiro os dados JSON embutidos na página (__NEXT_DATA__) e, se não
existirem, recorre aos links de anúncio no HTML. Se o site mudar, corre com
DEBUG_HTML=1 para guardar a página em debug/ e ajustar este ficheiro.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..modelo import Anuncio, area_do_texto, para_numero

BASE = "https://www.custojusto.pt"


def _url_pesquisa(pesquisa: str) -> str:
    return f"{BASE}/portugal/q/{quote(pesquisa)}"


def _candidatos_json(no, saida):
    """Percorre o JSON e recolhe objetos com cara de anúncio."""
    if isinstance(no, dict):
        titulo = no.get("title") or no.get("subject")
        ident = no.get("listID") or no.get("listId") or no.get("adId") or no.get("id")
        tem_preco = any(k in no for k in ("price", "priceValue", "listPrice"))
        tem_url = any(k in no for k in ("url", "link", "href"))
        if isinstance(titulo, str) and ident and (tem_preco or tem_url):
            saida.append(no)
        for v in no.values():
            _candidatos_json(v, saida)
    elif isinstance(no, list):
        for v in no:
            _candidatos_json(v, saida)


def _do_json(sopa) -> list[Anuncio]:
    script = sopa.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []
    candidatos = []
    _candidatos_json(json.loads(script.string), candidatos)
    anuncios = []
    for c in candidatos:
        ident = c.get("listID") or c.get("listId") or c.get("adId") or c.get("id")
        url = c.get("url") or c.get("link") or c.get("href") or ""
        loc = c.get("location") or c.get("locationName") or c.get("municipality") or ""
        if isinstance(loc, dict):
            loc = ", ".join(str(v) for v in loc.values() if isinstance(v, str))
        anuncios.append(Anuncio(
            fonte="CustoJusto",
            id=f"cj:{ident}",
            titulo=c.get("title") or c.get("subject") or "",
            preco=para_numero(c.get("price") or c.get("priceValue") or c.get("listPrice")),
            local=str(loc),
            url=urljoin(BASE, url) if url else "",
            descricao=str(c.get("body") or c.get("description") or ""),
            area=para_numero(c.get("size") or c.get("area")) or area_do_texto(
                f"{c.get('title') or c.get('subject') or ''} {c.get('body') or ''}"),
        ))
    return anuncios


def _do_html(sopa) -> list[Anuncio]:
    """Plano B: links de anúncio terminam num id numérico longo."""
    anuncios = {}
    for a in sopa.find_all("a", href=True):
        href = urljoin(BASE, a["href"])
        m = re.search(r"custojusto\.pt/.+?(\d{7,})(?:$|[/?#])", href)
        if not m:
            continue
        texto = a.get_text(" ", strip=True)
        preco_txt = re.search(r"\d{1,3}(?:[\s.]\d{3})*(?:,\d{1,2})?\s?€", texto)
        titulo = (texto[:preco_txt.start()] if preco_txt else texto).strip() or texto
        anuncios[m.group(1)] = Anuncio(
            fonte="CustoJusto",
            id=f"cj:{m.group(1)}",
            titulo=titulo[:150],
            preco=para_numero(preco_txt.group(0)) if preco_txt else None,
            local="",
            url=href,
            area=area_do_texto(titulo),
        )
    return list(anuncios.values())


def procurar(sessao, procura) -> list[Anuncio]:
    r = sessao.get(_url_pesquisa(procura["pesquisa"]), timeout=25)
    r.raise_for_status()

    if os.getenv("DEBUG_HTML"):
        Path("debug").mkdir(exist_ok=True)
        Path("debug/custojusto.html").write_text(r.text, encoding="utf-8")

    sopa = BeautifulSoup(r.text, "html.parser")
    anuncios = _do_json(sopa) or _do_html(sopa)

    vistos, unicos = set(), []
    for a in anuncios:
        if a.area is None:
            a.area = extrair_area(f"{a.titulo} {a.descricao}")
        if a.id not in vistos:
            vistos.add(a.id)
            unicos.append(a)
    return unicos

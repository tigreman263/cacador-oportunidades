"""Base do Drive: anúncios que o utilizador junta à mão numa pasta do Google Drive.

A pasta está organizada como OLX/base/<distrito>/<concelho>/<família>.csv (ex.: "carros.csv").
Cada CSV (separado por ";") tem as colunas:
  origem;especialidade;subcategoria;titulo;preco;preco_num;negociavel;distrito;concelho;localidade;
  marca;modelo;ano;km;combustivel;estado;tipologia;area_m2;detalhes;profissional;publicado;atualizado;
  link;descarregado_em

O bot nunca vai ao site de origem: só lê os ficheiros. Cada procura escolhe as famílias que quer
(campo "familias_drive"), porque a base tem milhares de ficheiros. Os ficheiros ficam guardados
numa cópia local (estado/drive_cache, que não vai para o repositório público) e só se descarregam
de novo quando mudam no Drive.

Acesso: uma "conta de serviço" do Google com a pasta partilhada com ela (só leitura).
A chave (JSON) vai no segredo GOOGLE_DRIVE_CHAVE.
"""
import csv
import hashlib
import io
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..texto import encontrar, normalizar, numero

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/drive/v3/files"
ESCOPO = ["https://www.googleapis.com/auth/drive.readonly"]
CACHE = Path(__file__).resolve().parent.parent.parent / "estado" / "drive_cache"
# Palavras da pesquisa que não ajudam a escolher anúncios (no CustoJusto o site trata disto).
VAZIAS = {"venda", "vendo", "vende", "de", "da", "do", "das", "dos", "para", "com", "em", "e", "a", "o"}

_linhas = {}      # família -> lista de anúncios já lidos nesta execução
_sessao = None    # sessão autenticada no Google (criada uma vez por execução)


def configurado() -> bool:
    return bool(os.environ.get("GOOGLE_DRIVE_CHAVE"))


def _sessao_google():
    global _sessao
    if _sessao is None:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        info = json.loads(os.environ["GOOGLE_DRIVE_CHAVE"])
        _sessao = AuthorizedSession(service_account.Credentials.from_service_account_info(info, scopes=ESCOPO))
    return _sessao


def _listar(sessao, familias: list) -> list:
    """Todos os CSV destas famílias que a conta de serviço consegue ver."""
    nomes = " or ".join("name = '%s.csv'" % f.replace("'", "\\'") for f in familias)
    q = f"mimeType = 'text/csv' and trashed = false and ({nomes})"
    res, token = [], None
    while True:
        params = {"q": q, "pageSize": 1000, "fields": "nextPageToken, files(id, name, modifiedTime)",
                  "includeItemsFromAllDrives": "true", "supportsAllDrives": "true"}
        if token:
            params["pageToken"] = token
        r = sessao.get(API, params=params, timeout=60)
        r.raise_for_status()
        d = r.json()
        res.extend(d.get("files") or [])
        token = d.get("nextPageToken")
        if not token:
            return res


def _ficheiro(sessao, f: dict, indice: dict) -> str:
    """Conteúdo do CSV: da cópia local se não mudou no Drive, senão descarrega."""
    destino = CACHE / f"{f['id']}.csv"
    if indice.get(f["id"]) == f["modifiedTime"] and destino.exists():
        return destino.read_text(encoding="utf-8")
    r = sessao.get(f"{API}/{f['id']}", params={"alt": "media", "supportsAllDrives": "true"}, timeout=60)
    r.raise_for_status()
    texto = r.content.decode("utf-8-sig", errors="replace")
    destino.write_text(texto, encoding="utf-8")
    indice[f["id"]] = f["modifiedTime"]
    return texto


def _sem_parte(titulo: str, *partes) -> str:
    """Junta marca/modelo/ano ao título quando o vendedor não os escreveu (ajuda os filtros de palavras)."""
    t = normalizar(titulo)
    extra = [str(p).strip() for p in partes if p and str(p).strip() and normalizar(p) not in t]
    return f"{titulo} ({' '.join(extra)})" if extra else titulo


def converter(l: dict) -> dict:
    link = (l.get("link") or "").strip()
    m = re.search(r"-(ID\w+)\.html", link)
    ident = m.group(1) if m else hashlib.sha1((link or l.get("titulo") or "").encode()).hexdigest()[:12]
    marca = l.get("marca") or (l.get("subcategoria") if l.get("modelo") or l.get("ano") else "")
    titulo = _sem_parte((l.get("titulo") or "").strip(), marca, l.get("modelo"), l.get("tipologia"))
    detalhes = [l.get("detalhes"), l.get("estado"), l.get("combustivel"),
                f"{l['ano']}" if l.get("ano") else "", f"{l['km']} km" if l.get("km") else "",
                "negociavel" if (l.get("negociavel") or "").strip().lower() == "sim" else ""]
    preco = numero(l.get("preco_num")) if l.get("preco_num") else numero(l.get("preco"))
    return {
        "id": f"drive-{ident}",
        "fonte": "OLX (Drive)",
        "titulo": titulo,
        "descricao": " | ".join(x for x in detalhes if x),
        "preco": preco,
        "area": numero(l.get("area_m2")) or None,
        "url": link or None,
        "categoria": normalizar(f"{l.get('especialidade') or ''} {l.get('subcategoria') or ''}"),
        "cidade": (l.get("concelho") or "").strip() or None,
        "distrito": (l.get("distrito") or "").strip() or None,
        "lat": None, "lon": None,
        "publicado": (l.get("publicado") or "").strip() or None,
    }


def ler_csv(texto: str) -> list:
    texto = texto.lstrip("﻿")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    # Alguns cabeçalhos vêm com "\_" (ex.: "preco\_num").
    leitor.fieldnames = [(c or "").replace("\\_", "_").strip() for c in leitor.fieldnames or []]
    res = []
    for l in leitor:
        if not (l.get("titulo") or "").strip():
            continue
        a = converter({k: (v or "").strip() for k, v in l.items() if k})
        if a["preco"]:
            res.append(a)
    return res


def carregar(familias: list) -> dict:
    """{família: [anúncios]} para as famílias pedidas (lê cada família uma vez por execução)."""
    falta = [f for f in familias if f not in _linhas]
    if falta:
        sessao = _sessao_google()
        CACHE.mkdir(parents=True, exist_ok=True)
        ind_path = CACHE / "indice.json"
        try:
            indice = json.loads(ind_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            indice = {}
        ficheiros = _listar(sessao, falta)
        for f in falta:
            _linhas[f] = []
        novos = sum(1 for f in ficheiros if indice.get(f["id"]) != f["modifiedTime"])

        def um(f):
            try:
                return f["name"][:-4], ler_csv(_ficheiro(sessao, f, indice))
            except Exception as e:
                log.warning("Drive: não consegui ler %s (%s): %s", f["name"], f["id"], e)
                return f["name"][:-4], []

        with ThreadPoolExecutor(max_workers=6) as ex:
            for fam, anuncios in ex.map(um, ficheiros):
                _linhas.setdefault(fam, []).extend(anuncios)
        ind_path.write_text(json.dumps(indice), encoding="utf-8")
        log.info("Drive: %d ficheiros (%d descarregados de novo) em %s", len(ficheiros), novos, ", ".join(falta))
    return {f: _linhas.get(f, []) for f in familias}


def palavras_pesquisa(pesquisa: str) -> list:
    return [w for w in normalizar(pesquisa).split() if len(w) >= 2 and w not in VAZIAS]


def corresponde(a: dict, palavras: list) -> bool:
    """Como a pesquisa de um site: basta uma palavra da pesquisa no título ou nos detalhes.
    Os filtros da procura (palavras obrigatórias, a ignorar…) apertam depois."""
    if not palavras:
        return True
    return bool(encontrar(normalizar(f"{a['titulo']} {a['descricao']} {a['categoria']}"), palavras))


def procurar(sessao, pesquisa: str, familias=None):
    """sessao (a do bot) não é usada: o Drive tem a sua sessão autenticada."""
    familias = [f for f in (familias or []) if f]
    if not familias:
        log.warning("Drive: a procura não tem famílias escolhidas ('%s'); nada a ler.", pesquisa)
        return
    if not configurado():
        log.warning("Drive: falta o segredo GOOGLE_DRIVE_CHAVE; a base do Drive fica de fora.")
        return
    palavras = palavras_pesquisa(pesquisa)
    vistos = set()
    for lista in carregar(familias).values():
        for a in lista:
            if a["id"] not in vistos and corresponde(a, palavras):
                vistos.add(a["id"])
                yield a

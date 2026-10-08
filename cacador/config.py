"""Lê config.json e completa o que faltar com as propostas de docs/regras.json."""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REGRAS = RAIZ / "docs" / "regras.json"
CONFIG = RAIZ / "config.json"


def carregar():
    regras = json.loads(REGRAS.read_text(encoding="utf-8"))
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}

    geral = {r["chave"]: r["proposta"] for r in regras["geral"]}
    geral.update({k: v for k, v in (cfg.get("geral") or {}).items() if v is not None})

    sinais = {r["chave"]: r["proposta"] for r in regras["sinais"]}
    sinais.update({k: v for k, v in (cfg.get("sinais") or {}).items() if isinstance(v, list)})

    modelos = regras.get("modelos", {})
    procuras = []
    for p in cfg.get("procuras", []):
        modelo = modelos.get(p.get("tipo") or "outro", {})
        completa = {}
        for r in regras["procura"]:
            k, v = r["chave"], p.get(r["chave"])
            padrao = modelo.get(k, r["proposta"])
            if r["tipo"] == "zona":
                completa[k] = v if isinstance(v, dict) else {"modo": "pais"}
            elif r["tipo"] in ("lista", "fontes"):
                completa[k] = v if isinstance(v, list) else (padrao or [])
            elif v in (None, ""):
                completa[k] = padrao if r["tipo"] in ("sim_nao", "escolha") else None
            else:
                completa[k] = v
        completa["nome"] = completa["nome"] or "Sem nome"
        if isinstance(p.get("zonas"), list):  # formato antigo
            completa["zonas"] = p["zonas"]
        if completa["pesquisa"]:
            procuras.append(completa)
    return geral, sinais, procuras

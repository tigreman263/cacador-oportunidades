"""Decisão: o anúncio interessa? Qual é o preço normal? É boa compra, a rever ou nada?"""
from collections import defaultdict
from statistics import median

from .texto import encontrar, normalizar, sem_acento

DIAS_MERCADO = 120  # amostras mais antigas que isto deixam de contar para o preço normal
DIA = 86400


def regras_efetivas(regras: dict, config: dict):
    """Junta as propostas do regras.json com o que o utilizador mudou no config.json."""
    geral = {}
    for r in regras["geral"]:
        v = (config.get("geral") or {}).get(r["chave"])
        geral[r["chave"]] = r["proposta"] if v is None else v
    sinais = {}
    for r in regras["sinais"]:
        v = (config.get("sinais") or {}).get(r["chave"])
        sinais[r["chave"]] = v if isinstance(v, list) else r["proposta"]
    return geral, sinais


def chave_procura(p: dict) -> str:
    return p.get("id") or "nome:" + sem_acento(p.get("nome"))


def unidade_de(p: dict) -> str:
    return "€/m²" if p.get("comparar_por") == "preco_m2" else "€"


def _juntar(*listas):
    return list(dict.fromkeys(x for l in listas for x in (l or [])))


def avaliar_texto(a: dict, p: dict, sinais: dict):
    """Filtro de palavras. Devolve {grupo, problemas, sinais} ou None se o anúncio não interessa."""
    tit = normalizar(a.get("titulo"))
    txt = normalizar(f"{a.get('titulo', '')} {a.get('descricao', '')}")
    if any(not encontrar(tit, [w]) for w in p.get("incluir") or []):
        return None
    alt = p.get("alternativas") or []
    if alt and not encontrar(tit, alt):
        return None
    # As palavras a ignorar também valem para a categoria do site (ex.: "pecas" apanha "Peças e acessórios").
    if encontrar(f"{tit} {normalizar(a.get('categoria'))}", p.get("excluir")):
        return None
    if encontrar(txt, _juntar(sinais.get("problemas_graves"), p.get("graves_extra"))):
        return None
    grupos = encontrar(tit, p.get("grupos"), inteira=True)
    return {
        "grupo": grupos[0] if grupos else None,
        "problemas": encontrar(txt, _juntar(sinais.get("problemas_a_rever"), p.get("problemas_extra"))),
        "sinais": encontrar(txt, sinais.get("urgencia")),
    }


def valor_comparavel(a: dict, p: dict):
    if not a.get("preco") or a["preco"] <= 0:
        return None
    if unidade_de(p) == "€/m²":
        return a["preco"] / a["area"] if a.get("area") and a["area"] > 0 else None
    return float(a["preco"])


def podar_amostras(amostras: dict, agora: float):
    for k in list(amostras):
        if agora - amostras[k]["t"] > DIAS_MERCADO * DIA:
            del amostras[k]


def conjuntos_mercado(amostras: dict, unidade: str):
    """{'todos': {id: valor}, '<grupo>': {id: valor}} só com anúncios sem problemas."""
    c = defaultdict(dict)
    for i, s in amostras.items():
        if s.get("u") != unidade or s.get("p"):
            continue
        c["todos"][i] = s["v"]
        if s.get("g"):
            c[s["g"]][i] = s["v"]
    return c


def resumo_mercado(conj: dict, unidade: str) -> dict:
    return {g: {"mediana": round(median(v.values()), 2), "amostras": len(v), "unidade": unidade}
            for g, v in conj.items() if v}


def referencia(conj: dict, grupo, proprio_id: str, minimo: int):
    """Preço normal para comparar este anúncio (sem contar com ele próprio). Um T2 só com T2."""
    base = conj.get(grupo if grupo else "todos") or {}
    valores = [v for i, v in base.items() if i != proprio_id]
    if len(valores) < max(1, int(minimo)):
        return None, len(valores)
    return median(valores), len(valores)


def classificar(info: dict, valor: float, mediana: float, geral: dict, p: dict):
    """Devolve ('boa'|'rever'|None, desconto)."""
    if not mediana or mediana <= 0:
        return None, 0.0
    desconto = 1 - valor / mediana
    if info["problemas"]:
        minimo = float(geral["desconto_minimo_com_problemas"] or 0)
        return ("rever" if minimo <= 0 or desconto >= minimo / 100 else None), desconto
    if valor < float(geral["limite_burla"]) / 100 * mediana:
        return None, desconto  # bom demais para ser verdade
    exigido = p.get("desconto_minimo")
    exigido = float(geral["desconto_minimo"] if exigido is None else exigido)
    if info["sinais"]:
        exigido -= float(geral["bonus_urgencia"] or 0)
    return ("boa" if desconto >= max(exigido, 0) / 100 else None), desconto

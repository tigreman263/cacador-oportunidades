"""Classifica cada anúncio: "boa" (boa compra), "rever" (bom preço mas com
problemas razoáveis) ou "descartado". O preço de mercado é aprendido pelo bot."""
import re
import statistics
import time
from dataclasses import dataclass, field

from .modelo import normalizar

MAX_REGISTOS = 1500
DIAS_HISTORICO = 120


@dataclass
class Avaliacao:
    categoria: str                      # "boa" | "rever" | "descartado"
    motivo: str = ""
    desconto: float | None = None       # 0.22 = 22% abaixo da mediana
    mediana: float | None = None
    amostras: int = 0
    grupo: str | None = None
    sinais: list = field(default_factory=list)
    problemas: list = field(default_factory=list)
    por_m2: bool = False
    unidade: str = "€"                  # "€" ou "€/m²"
    valor: float | None = None          # preço ou preço por m²
    area: float | None = None


def _texto(anuncio):
    return normalizar(f"{anuncio.titulo} {anuncio.descricao}")


def _contem(texto, termos):
    return [t for t in termos if normalizar(t) and normalizar(t) in texto]


_RE_M2 = re.compile(r"(\d{1,3}(?:[ .]\d{3})+|\d+)(?:,\d+)?\s?(?:m2|m²|mt2|mts2|metros quadrados)")
_RE_HA = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:ha|hectares?)\b")


def area_do(anuncio):
    """Área em m²: a indicada pelo site ou lida do título/descrição."""
    if anuncio.area:
        return anuncio.area
    texto = f"{anuncio.titulo} {anuncio.descricao}".lower()
    m = _RE_M2.search(texto)
    if m:
        return float(re.sub(r"[ .]", "", m.group(1)))
    m = _RE_HA.search(texto)
    if m:
        return float(m.group(1).replace(",", ".")) * 10000
    return None


def valor_comparavel(anuncio, procura):
    """Preço total, ou preço por m² se a procura comparar por m²."""
    if anuncio.preco is None:
        return None
    if procura.get("comparar_por") == "preco_m2":
        area = area_do(anuncio)
        return anuncio.preco / area if area else None
    return anuncio.preco


def grupo_do(anuncio, procura):
    texto = f" {normalizar(anuncio.titulo)} "
    for g in procura.get("grupos") or []:
        g = normalizar(str(g))
        if f" {g} " in texto or f" {g}cc " in texto:
            return g
    return None


def sinais_da(procura, sinais):
    """Sinais gerais + os próprios desta procura."""
    return {
        "urgencia": sinais["urgencia"],
        "rever": list(sinais["problemas_a_rever"]) + list(procura.get("problemas_extra") or []),
        "graves": list(sinais["problemas_graves"]) + list(procura.get("graves_extra") or []),
    }


def valor_comparavel(anuncio, procura):
    """Preço total, ou preço por m² quando a procura compara por área."""
    if anuncio.preco is None:
        return None
    if procura.get("comparar_por") == "preco_m2":
        return anuncio.preco / anuncio.area if anuncio.area else None
    return anuncio.preco


def tem_problema(anuncio, procura, sinais):
    s, t = sinais_da(procura, sinais), _texto(anuncio)
    return bool(_contem(t, s["rever"]) or _contem(t, s["graves"]))


def limpar_historico(registos):
    limite = time.time() - DIAS_HISTORICO * 86400
    vivos = {k: v for k, v in registos.items() if v.get("t", 0) >= limite}
    if len(vivos) > MAX_REGISTOS:
        vivos = dict(sorted(vivos.items(), key=lambda kv: kv[1]["t"])[-MAX_REGISTOS:])
    return vivos


def _mediana_limpa(precos):
    m0 = statistics.median(precos)
    limpos = [p for p in precos if 0.5 * m0 <= p <= 2 * m0]
    return statistics.median(limpos), len(limpos)


def referencia(registos, grupo, minimo, excluir_id=None):
    def v(r):
        return r.get("v", r.get("p"))
    validos = [r for k, r in registos.items() if k != excluir_id and v(r) and not r.get("x")]
    do_grupo = [v(r) for r in validos if r.get("g") == grupo]
    todos = [v(r) for r in validos]
    if grupo and len(do_grupo) >= minimo:
        return (*_mediana_limpa(do_grupo), grupo)
    if len(todos) >= minimo:
        return (*_mediana_limpa(todos), None)
    return None, len(todos), None


def avaliar(anuncio, procura, registos, geral, sinais):
    texto = _texto(anuncio)
    s = sinais_da(procura, sinais)

    graves = _contem(texto, s["graves"])
    if graves:
        return Avaliacao("descartado", f"problema grave: {graves[0]}", problemas=graves)
    if anuncio.preco is None:
        return Avaliacao("descartado", "sem preço")
    if procura.get("preco_max") is not None and anuncio.preco > procura["preco_max"]:
        return Avaliacao("descartado", "acima do orçamento")

    por_m2 = procura.get("comparar_por") == "preco_m2"
    unidade = "€/m²" if por_m2 else "€"
    valor = valor_comparavel(anuncio, procura)
    if valor is None:
        return Avaliacao("descartado", "sem área indicada", unidade=unidade)

    grupo = grupo_do(anuncio, procura)
    mediana, n, grupo_usado = referencia(registos, grupo, geral["minimo_amostras"], anuncio.id)
    if mediana is None:
        return Avaliacao("descartado", f"a aprender o mercado ({n}/{geral['minimo_amostras']})", amostras=n)

    desconto = 1 - valor / mediana
    problemas = _contem(texto, s["rever"])
    urgencia = _contem(texto, s["urgencia"])
    base = dict(desconto=desconto, mediana=mediana, amostras=n, grupo=grupo_usado,
                sinais=urgencia, problemas=problemas, unidade=unidade, valor=valor,
                area=area_do(anuncio) if por_m2 else None)

    # preço muito baixo sem explicação = suspeito; com um problema declarado
    # (ex.: "para recuperar") o preço baixo é esperado e o anúncio vai para "A rever"
    if not problemas and valor < mediana * geral["limite_burla"] / 100:
        return Avaliacao("descartado", "preço suspeito (possível burla)", **base)
    if desconto < 0:
        return Avaliacao("descartado", f"{-desconto:.0%} acima do mercado", **base)

    if problemas:
        if desconto >= geral["desconto_minimo_com_problemas"] / 100:
            return Avaliacao("rever", f"bom preço mas: {', '.join(problemas)}", **base)
        return Avaliacao("descartado", f"tem problemas e só {desconto:.0%} abaixo", **base)

    minimo = procura.get("desconto_minimo")
    if minimo is None:
        minimo = geral["desconto_minimo"]
    exigido = minimo / 100 - (geral["bonus_urgencia"] / 100 if urgencia else 0)
    if desconto >= exigido:
        return Avaliacao("boa", "boa compra", **base)
    return Avaliacao("descartado", f"só {desconto:.0%} abaixo do mercado", **base)

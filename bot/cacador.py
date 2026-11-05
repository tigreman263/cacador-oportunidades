"""Uma verificação completa: lê config e regras, percorre as fontes, atualiza o mercado,
classifica os anúncios, grava docs/dados.json e estado/estado.json e devolve os alertas novos."""
import json
import logging
import time
from pathlib import Path

from . import analise as A
from .zonas import Localidades, dentro_da_zona

log = logging.getLogger(__name__)
RAIZ = Path(__file__).resolve().parent.parent


def ler_json(caminho: Path, defeito):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defeito


def gravar_json(caminho: Path, dados, compacto=False):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")) if compacto \
        else json.dumps(dados, ensure_ascii=False, indent=1)
    caminho.write_text(texto + "\n", encoding="utf-8")


def endereco_olx(p: dict) -> str:
    from .fontes.olx import endereco_pesquisa
    return endereco_pesquisa(p)


def buscar_anuncios(sessao, p: dict, fontes: dict, pausa: float = 2.0) -> list:
    vistos, res = set(), []
    for nome in p.get("fontes") or ["olx", "custojusto"]:
        f = fontes.get(nome)
        if not f:
            continue
        try:
            if nome == "autouncle" and (p.get("tipo") or "outro") not in ("carro", "outro"):
                continue  # o AutoUncle só tem carros
            extra = ({"categoria": p.get("categoria") or ""} if nome == "custojusto"
                     else {"tipo_carro": p.get("categoria_autouncle") or "", "preco_max": p.get("preco_max")} if nome == "autouncle"
                     else {})
            for a in f(sessao, p["pesquisa"], **extra):
                if a["id"] not in vistos:
                    vistos.add(a["id"])
                    res.append(a)
        except Exception as e:
            log.warning("%s falhou em '%s': %s", nome, p.get("nome"), e)
        time.sleep(pausa)
    return res


def processar(config, regras, dados, estado, loc, anuncios_por_procura: dict, agora: float):
    """Parte "pura" (sem rede), fácil de testar. Altera dados/estado e devolve (boas, rever) novas para alertar."""
    geral, sinais = A.regras_efetivas(regras, config)
    procuras = [p for p in config.get("procuras") or [] if p.get("ativa") is not False and p.get("pesquisa")]
    chaves_ativas = {A.chave_procura(p) for p in procuras}
    anuncios = dados.setdefault("anuncios", {})
    mercado_out = {}
    amostras_todas = estado.setdefault("amostras", {})
    alertados = estado.setdefault("alertados", {})
    boas, rever = [], []

    for p in procuras:
        chave, unidade = A.chave_procura(p), A.unidade_de(p)
        amostras = amostras_todas.setdefault(chave, {})
        zona = p.get("zona") or {"modo": "pais"}
        candidatos = []
        for a in anuncios_por_procura.get(chave, []):
            info = A.avaliar_texto(a, p, sinais)
            valor = A.valor_comparavel(a, p) if info else None
            if valor is None:
                continue
            local = loc.resolver(a.get("cidade"), a.get("distrito"), a.get("lat"), a.get("lon")) if loc else None
            na_zona, km = dentro_da_zona(zona, local)
            # Imóveis: o preço/m² muda muito de região, por isso o mercado é só o da zona escolhida.
            if unidade == "€/m²" and not na_zona:
                continue
            anterior = amostras.get(a["id"]) or {}
            amostras[a["id"]] = {"v": round(valor, 2), "g": info["grupo"], "t": agora, "u": unidade,
                                 "p": bool(info["problemas"]), "preco": a["preco"],
                                 "max": max(a["preco"], anterior.get("max") or 0)}
            if na_zona and (not p.get("preco_max") or a["preco"] <= p["preco_max"]):
                candidatos.append((a, info, valor, local, km))

        A.podar_amostras(amostras, agora)
        conj = A.conjuntos_mercado(amostras, unidade)
        mercado_out[p.get("nome") or "Sem nome"] = A.resumo_mercado(conj, unidade)

        for a, info, valor, local, km in candidatos:
            mediana, n = A.referencia(conj, info["grupo"], a["id"], geral["minimo_amostras"])
            categoria, desconto = A.classificar(info, valor, mediana, geral, p) if mediana else (None, 0)
            antigo = anuncios.get(a["id"])
            if not categoria:
                anuncios.pop(a["id"], None)  # deixou de ser oportunidade
                continue
            maximo = amostras[a["id"]]["max"]
            reg = {
                "procura": p.get("nome"), "procura_id": chave, "tipo": p.get("tipo") or "outro",
                "categoria": categoria, "titulo": a["titulo"], "preco": a["preco"],
                "preco_antes": maximo if maximo > a["preco"] else None,
                "desconto": round(desconto, 3), "mediana": round(mediana, 2), "unidade": unidade,
                "valor": round(valor, 2), "area": a.get("area"), "amostras": n, "grupo": info["grupo"],
                "sinais": info["sinais"], "problemas": info["problemas"], "fonte": a["fonte"],
                "local": (local or {}).get("nome") or a.get("cidade"), "url": a.get("url"),
                "olx_pesquisa": endereco_olx(p),
                "primeiro": (antigo or {}).get("primeiro", agora), "ultimo": agora, "km": km,
            }
            anuncios[a["id"]] = reg
            ja = alertados.get(a["id"])
            if ja is None or a["preco"] < ja["preco"]:
                if categoria == "boa":
                    boas.append(reg)
                elif geral["alertar_com_problemas"]:
                    rever.append(reg)
                alertados[a["id"]] = {"preco": a["preco"], "t": agora}

    # Limpeza: procuras apagadas/pausadas e anúncios antigos (provavelmente vendidos).
    limite = float(geral["dias_na_listagem"]) * A.DIA
    for i in list(anuncios):
        r = anuncios[i]
        if r.get("procura_id") not in chaves_ativas or agora - r.get("primeiro", agora) > limite:
            del anuncios[i]
    for k in list(amostras_todas):
        if k not in chaves_ativas and not any(agora - s["t"] <= A.DIAS_MERCADO * A.DIA for s in amostras_todas[k].values()):
            del amostras_todas[k]
    for i in list(alertados):
        if agora - alertados[i]["t"] > A.DIAS_MERCADO * A.DIA:
            del alertados[i]

    dados["mercado"] = mercado_out
    dados["atualizado"] = agora
    return boas, rever


FOLGA_SEGUNDOS = 120  # o despertador pode tocar uns minutos antes ou depois da hora certa


def e_altura(geral: dict, estado: dict, agora: float) -> bool:
    """Nas execuções agendadas, só procura quando já passou o intervalo escolhido nas regras."""
    ultima = estado.get("ultima_verificacao")
    if ultima is None:
        return True
    intervalo = max(15, float(geral.get("intervalo_minutos") or 15)) * 60
    return agora - ultima >= intervalo - FOLGA_SEGUNDOS


def correr(sessao, fontes: dict, raiz: Path = RAIZ, agora: float = None, agendada: bool = False):
    """Devolve (boas, rever), ou None se for uma execução agendada e ainda não for altura."""
    agora = agora or time.time()
    config = ler_json(raiz / "config.json", {"procuras": []})
    regras = ler_json(raiz / "docs" / "regras.json", None)
    if not regras:
        raise SystemExit("Falta docs/regras.json")
    dados = ler_json(raiz / "docs" / "dados.json", {"anuncios": {}, "mercado": {}})
    estado = ler_json(raiz / "estado" / "estado.json", {"amostras": {}, "alertados": {}})
    if agendada:
        geral, _ = A.regras_efetivas(regras, config)
        if not e_altura(geral, estado, agora):
            falta = (estado["ultima_verificacao"] + float(geral.get("intervalo_minutos") or 15) * 60 - agora) / 60
            log.info("Ainda não é altura (intervalo de %s min; faltam cerca de %d min).", geral.get("intervalo_minutos"), max(1, round(falta)))
            return None

    loc_json = ler_json(raiz / "docs" / "localidades.json", None)
    loc = Localidades(loc_json) if loc_json else None
    if not loc:
        log.warning("Sem docs/localidades.json: só as procuras com 'Todo o país' vão encontrar anúncios.")

    por_procura = {}
    for p in config.get("procuras") or []:
        if p.get("ativa") is False or not p.get("pesquisa"):
            continue
        lista = buscar_anuncios(sessao, p, fontes)
        log.info("%s: %d anúncios recebidos", p.get("nome"), len(lista))
        por_procura[A.chave_procura(p)] = lista

    boas, rever = processar(config, regras, dados, estado, loc, por_procura, agora)
    estado["ultima_verificacao"] = agora
    gravar_json(raiz / "docs" / "dados.json", dados)
    gravar_json(raiz / "estado" / "estado.json", estado, compacto=True)
    log.info("Novas: %d boas, %d a rever. Na lista: %d.", len(boas), len(rever), len(dados["anuncios"]))
    return boas, rever

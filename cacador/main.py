"""Caçador de Oportunidades — procura boas compras em todas as procuras ativas.

Uso:
  python -m cacador.main                    # verificação normal
  python -m cacador.main --teste            # mostra no ecrã, não envia nem grava
  python -m cacador.main --testar-whatsapp  # envia uma mensagem de teste
"""
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import requests

from . import config
from .avaliar import (avaliar, grupo_do, limpar_historico, referencia, tem_problema,
                      valor_comparavel)
from .fontes import FONTES
from .localidades import Localizador, dentro_da_zona, distancia_km
from .modelo import extrair_area, normalizar
from .notificar import enviar, enviar_alertas

RAIZ = Path(__file__).resolve().parent.parent
FICHEIRO_ESTADO = RAIZ / "estado" / "vistos.json"
FICHEIRO_LISTAGEM = RAIZ / "docs" / "dados.json"

CABECALHOS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "pt-PT,pt;q=0.9",
}


def carregar_env():
    env = RAIZ / ".env"
    if env.exists():
        for linha in env.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def slug(texto):
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")


def ler_json(caminho, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def onde_fica(anuncio, localizador):
    """Coordenadas, concelho e distrito do anúncio (None se não se souber)."""
    if localizador is None:
        return None
    if anuncio.lat is not None and anuncio.lon is not None:
        return localizador.mais_proximo(anuncio.lat, anuncio.lon)
    return localizador.localizar(anuncio.local)


def na_zona(anuncio, procura, localizador):
    zona = procura.get("zona") or {}
    if zona.get("modo", "pais") != "pais":
        if localizador is None:
            return True  # sem base de localidades não filtra (aviso no registo)
        anuncio._onde = onde_fica(anuncio, localizador)
        return dentro_da_zona(anuncio._onde, zona)
    # formato antigo: lista de nomes escritos à mão
    zonas = [normalizar(z) for z in procura.get("zonas") or [] if normalizar(z)]
    if not zonas:
        return True
    onde = normalizar(anuncio.local) if anuncio.local else normalizar(f"{anuncio.titulo} {anuncio.descricao}")
    return any(z in onde for z in zonas)


def e_relevante(anuncio, procura, localizador=None):
    """É o produto certo e na zona certa? (o preço é avaliado depois)"""
    texto = normalizar(anuncio.titulo)
    if any(normalizar(t) and normalizar(t) in texto for t in procura.get("excluir") or []):
        return False
    if not all(normalizar(t) in texto for t in procura.get("incluir") or []):
        return False
    alt = procura.get("alternativas") or []
    if alt and not any(normalizar(t) in texto for t in alt):
        return False
    return na_zona(anuncio, procura, localizador)


def distancia_ate_centro(anuncio, procura):
    zona, onde = procura.get("zona") or {}, getattr(anuncio, "_onde", None)
    c = zona.get("centro") or {}
    if zona.get("modo") == "raio" and onde and "lat" in c:
        return round(distancia_km(c["lat"], c["lon"], onde["lat"], onde["lon"]))
    return None


def resumo_mercado(registos, procura, geral):
    unidade = "€/m²" if procura.get("comparar_por") == "preco_m2" else "€"
    grupos = {}
    for g in [None] + [normalizar(str(x)) for x in procura.get("grupos") or []]:
        mediana, n, usado = referencia(registos, g, geral["minimo_amostras"])
        if mediana is not None and (g is None or usado == g):
            grupos[g or "todos"] = {"mediana": round(mediana, 1 if unidade == "€/m²" else 0),
                                    "amostras": n, "unidade": unidade}
    return grupos


def main():
    carregar_env()
    teste = "--teste" in sys.argv

    if "--testar-whatsapp" in sys.argv:
        ok = enviar("✅ Caçador de Oportunidades: ligação ao WhatsApp a funcionar!")
        sys.exit(0 if ok else 1)

    geral, sinais, procuras = config.carregar()
    precisa_mapa = any((p.get("zona") or {}).get("modo", "pais") != "pais" for p in procuras if p.get("ativa", True))
    localizador = Localizador.carregar() if precisa_mapa else None
    if precisa_mapa and localizador is None:
        print("[aviso] sem base de localidades: as zonas não estão a ser aplicadas")
    estado = ler_json(FICHEIRO_ESTADO, {})
    listagem = ler_json(FICHEIRO_LISTAGEM, {})
    anuncios_lista = listagem.get("anuncios", {})
    mercado = listagem.get("mercado", {})

    sessao = requests.Session()
    sessao.headers.update(CABECALHOS)
    agora = time.time()

    for procura in procuras:
        if not procura.get("ativa", True):
            continue
        # histórico separado por modo, para não misturar € com €/m²
        chave = slug(procura["nome"]) + ("-m2" if procura.get("comparar_por") == "preco_m2" else "")
        registos = estado.get(chave)
        if not isinstance(registos, dict):
            registos = {}

        relevantes, alguma_ok = {}, False
        for nome_fonte in procura.get("fontes") or list(FONTES):
            funcao = FONTES.get(nome_fonte)
            if not funcao:
                print(f"[aviso] fonte desconhecida: {nome_fonte}")
                continue
            try:
                resultados = funcao(sessao, procura)
            except Exception as erro:
                print(f"[erro] {procura['nome']} / {nome_fonte}: {erro}")
                continue
            alguma_ok = True
            for a in resultados:
                if a.area is None:
                    a.area = extrair_area(f"{a.titulo} {a.descricao}")
            bons = [a for a in resultados if e_relevante(a, procura, localizador)]
            print(f"{procura['nome']} / {nome_fonte}: {len(resultados)} lidos, {len(bons)} relevantes")
            relevantes.update({a.id: a for a in bons})
            time.sleep(random.uniform(2, 5))

        if not alguma_ok:
            continue

        # 1) aprender o mercado (anúncios com problemas não contam)
        precos_antigos = {k: v.get("preco", v.get("p")) for k, v in registos.items()}
        for a in relevantes.values():
            anterior = registos.get(a.id, {})
            registos[a.id] = {"p": a.preco, "v": valor_comparavel(a, procura),
                              "g": grupo_do(a, procura), "t": agora,
                              "a": anterior.get("a", False)}
            if tem_problema(a, procura, sinais):
                registos[a.id]["x"] = True

        # 2) avaliar anúncios novos ou que baixaram de preço
        boas, rever = [], []
        for a in relevantes.values():
            p_antes = precos_antigos.get(a.id, "novo")
            baixou = p_antes not in ("novo", None) and a.preco is not None and a.preco < p_antes
            if a.id in anuncios_lista:           # já na lista: só atualiza preço/data
                anuncios_lista[a.id].update(preco=a.preco, ultimo=agora)
            if p_antes != "novo" and not baixou:
                continue
            if registos[a.id]["a"] and not baixou:
                continue
            av = avaliar(a, procura, registos, geral, sinais)
            marca = {"boa": "✔", "rever": "?", "descartado": "·"}[av.categoria]
            print(f"  {marca} {a.titulo[:60]} — {av.motivo}")
            if av.categoria == "descartado":
                continue
            a._km = distancia_ate_centro(a, procura)
            item = (a, av, p_antes if baixou else None)
            (boas if av.categoria == "boa" else rever).append(item)
            anuncios_lista[a.id] = {
                "procura": procura["nome"], "categoria": av.categoria,
                "titulo": a.titulo, "preco": a.preco,
                "preco_antes": p_antes if baixou else None,
                "desconto": round(av.desconto, 3), "mediana": round(av.mediana, 2),
                "unidade": av.unidade, "valor": round(av.valor, 2), "area": av.area,
                "tipo": procura.get("tipo", "outro"),
                "amostras": av.amostras, "grupo": av.grupo,
                "sinais": av.sinais, "problemas": av.problemas,
                "fonte": a.fonte, "local": a.local, "url": a.url,
                "km": distancia_ate_centro(a, procura),
                "primeiro": anuncios_lista.get(a.id, {}).get("primeiro", agora),
                "ultimo": agora,
            }

        # 3) alertas: boas compras primeiro; problemas numa secção à parte
        boas.sort(key=lambda x: x[1].desconto, reverse=True)
        rever.sort(key=lambda x: x[1].desconto, reverse=True)
        a_enviar_rever = rever if geral["alertar_com_problemas"] else []
        if (boas or a_enviar_rever) and not enviar_alertas(procura["nome"], boas, a_enviar_rever, teste):
            continue  # não grava; tenta outra vez na próxima volta
        for a, _, _ in boas + rever:
            registos[a.id]["a"] = True

        estado[chave] = limpar_historico(registos)
        mercado[procura["nome"]] = resumo_mercado(estado[chave], procura, geral)

    # limpar listagem antiga
    limite = agora - geral["dias_na_listagem"] * 86400
    anuncios_lista = {k: v for k, v in anuncios_lista.items() if v.get("primeiro", 0) >= limite}

    if not teste:
        FICHEIRO_ESTADO.parent.mkdir(exist_ok=True)
        FICHEIRO_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, separators=(",", ":")))
        FICHEIRO_LISTAGEM.write_text(json.dumps(
            {"atualizado": agora, "anuncios": anuncios_lista, "mercado": mercado},
            ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

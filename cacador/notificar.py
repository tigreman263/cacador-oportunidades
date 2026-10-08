"""Envio de alertas por WhatsApp através do CallMeBot."""
import os
import time

import requests

URL = "https://api.callmebot.com/whatsapp.php"
POR_MENSAGEM = 4


def _euros(v, unidade="€"):
    if v is None:
        return "sem preço"
    if unidade == "€/m²":
        return f"{v:,.2f} €/m²".replace(",", " ").replace(".", ",") if v < 100 else f"{v:,.0f} €/m²".replace(",", " ")
    return f"{v:,.0f} €".replace(",", " ")


def _bloco(a, av, preco_antes, icone):
    linhas = [f"{icone} {a.titulo}"]
    preco = f"💶 {_euros(a.preco)}"
    if preco_antes:
        preco += f" (baixou de {_euros(preco_antes)})"
    if av.unidade == "€/m²":
        preco += f" · {_euros(av.valor, av.unidade)}"
        if av.area:
            preco += f" · {av.area:,.0f} m²".replace(",", " ")
    linhas.append(f"{preco} · {av.desconto:.0%} abaixo do mercado")
    ref = f"📊 Mediana {_euros(av.mediana, av.unidade)} ({av.amostras} anúncios"
    linhas.append(ref + (f", {av.grupo})" if av.grupo else ")"))
    if av.problemas:
        linhas.append(f"⚠️ Problema: {', '.join(av.problemas)}")
    if av.sinais:
        linhas.append(f"⏱️ Pressa: {', '.join(av.sinais)}")
    km = getattr(a, "_km", None)
    longe = f" (a {km} km)" if km is not None else ""
    linhas.append(f"📍 {a.local}{longe} · {a.fonte}" if a.local else f"📍 {a.fonte}{longe}")
    linhas.append(a.url)
    return "\n".join(linhas)


def mensagens(nome, boas, rever):
    """Parte os alertas em mensagens; boas compras vêm sempre primeiro."""
    saida = []
    for i in range(0, len(boas), POR_MENSAGEM):
        parte = boas[i:i + POR_MENSAGEM]
        cab = f"🔥 {nome} — {len(boas)} boa(s) compra(s)"
        saida.append(cab + "\n\n" + "\n\n".join(_bloco(*x, "🟢") for x in parte))
    for i in range(0, len(rever), POR_MENSAGEM):
        parte = rever[i:i + POR_MENSAGEM]
        cab = f"🟠 {nome} — {len(rever)} a rever (com problemas)"
        saida.append(cab + "\n\n" + "\n\n".join(_bloco(*x, "🟠") for x in parte))
    return saida


def enviar(texto, teste=False):
    telefone = os.getenv("CALLMEBOT_PHONE")
    chave = os.getenv("CALLMEBOT_APIKEY")
    if teste or not telefone or not chave:
        print("----- (modo teste: mensagem não enviada) -----")
        print(texto)
        print("----------------------------------------------")
        return True
    r = requests.get(URL, params={"phone": telefone, "text": texto, "apikey": chave}, timeout=30)
    ok = r.ok and "error" not in r.text.lower()
    if not ok:
        print(f"Erro CallMeBot ({r.status_code}): {r.text[:300]}")
    time.sleep(4)
    return ok


def enviar_alertas(nome, boas, rever, teste=False):
    tudo_ok = True
    for texto in mensagens(nome, boas, rever):
        tudo_ok &= enviar(texto, teste)
    return tudo_ok

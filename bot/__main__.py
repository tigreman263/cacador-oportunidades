"""python -m bot                  verificação normal (pesquisa, grava, envia alertas)
   python -m bot --sem-avisos     igual, mas só escreve os alertas no ecrã
   python -m bot --agendada       só procura se já passou o intervalo das regras (despertador)
   python -m bot --resumo         no fim manda um resumo no Telegram (botão "Procurar agora")
   python -m bot --telegram-teste mostra o chat id e envia uma mensagem de teste
   python -m bot --localidades    (re)cria docs/localidades.json a partir do GeoNames

No PC, os segredos podem ficar num ficheiro .env na raiz do projeto (não vai para o GitHub):
   TELEGRAM_TOKEN=123456789:AA...
   TELEGRAM_CHAT_ID=123456789
"""
import argparse
import logging
import os

import requests

from . import avisos, cacador, localidades, telegram
from .fontes import FONTES

AGENTE = "CacadorDeOportunidades/1.0 (bot pessoal de alertas; python-requests)"


def ler_env(caminho):
    try:
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def main():
    ap = argparse.ArgumentParser(prog="python -m bot")
    ap.add_argument("--sem-avisos", action="store_true", help="não envia alertas, só os mostra")
    ap.add_argument("--agendada", action="store_true", help="respeita o intervalo das regras")
    ap.add_argument("--resumo", action="store_true", help="manda um resumo no Telegram no fim (botão Procurar agora)")
    ap.add_argument("--telegram-teste", action="store_true", help="testa a ligação ao Telegram")
    ap.add_argument("--localidades", action="store_true", help="recria docs/localidades.json")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ler_env(cacador.RAIZ / ".env")

    sessao = requests.Session()
    sessao.headers.update({"User-Agent": AGENTE, "Accept-Language": "pt-PT,pt;q=0.9"})

    if args.telegram_teste:
        telegram.teste(sessao)
        return

    destino = cacador.RAIZ / "docs" / "localidades.json"
    if args.localidades or not destino.exists():
        try:
            d = localidades.gravar(destino, sessao)
            logging.info("localidades.json: %d distritos, %d concelhos, %d lugares",
                         len(d["distritos"]), len(d["concelhos"]), len(d["lugares"]))
        except Exception as e:
            logging.warning("Não foi possível criar localidades.json: %s", e)
        if args.localidades:
            return

    res = cacador.correr(sessao, FONTES, agendada=args.agendada)
    if res is None:
        return
    boas, rever = res
    avisos.enviar_todos(sessao, boas, rever, so_mostrar=args.sem_avisos)
    if args.resumo and telegram.configurado() and not args.sem_avisos:
        vistos = ", ".join(f"{n}: {c}" for n, c in cacador.CONTAGEM.items()) or "nenhuma procura ativa"
        novas = f"{len(boas)} boa(s) compra(s) e {len(rever)} a rever (enviadas acima)" if boas or rever else "sem oportunidades novas desta vez"
        telegram.enviar(sessao, [f"✅ Procura terminada — {novas}.\nAnúncios vistos: {vistos}."])


if __name__ == "__main__":
    main()

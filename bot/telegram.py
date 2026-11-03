"""Alertas no Telegram através de um bot próprio (grátis, sem limites práticos para uso pessoal).

Configuração (segredos do repositório no GitHub, ou variáveis de ambiente no PC):
  TELEGRAM_TOKEN    o token que o @BotFather te dá, ex.: 123456789:AA...
  TELEGRAM_CHAT_ID  o teu chat (ou de um grupo). Vários: separados por vírgula.
Para descobrir o chat id: envia uma mensagem ao teu bot e corre  python -m bot --telegram-teste
"""
import logging
import os
import time

API = "https://api.telegram.org/bot{token}/{metodo}"
log = logging.getLogger(__name__)


def configurado() -> bool:
    return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _chamar(sessao, metodo, **dados):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    r = sessao.post(API.format(token=token, metodo=metodo), json=dados, timeout=30)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not j.get("ok"):
        raise RuntimeError(j.get("description") or f"HTTP {r.status_code}")
    return j["result"]


def enviar(sessao, mensagens: list) -> bool:
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    ok = True
    for chat in chats:
        for i, m in enumerate(mensagens):
            if i:
                time.sleep(1)
            try:
                _chamar(sessao, "sendMessage", chat_id=chat, text=m, parse_mode="HTML",
                        disable_web_page_preview=len(mensagens) > 1 or m.count("<a ") > 1)
            except Exception as e:
                log.warning("Telegram (chat %s): %s", chat, e)
                ok = False
    return ok


def teste(sessao):
    """Mostra os chats que falaram com o bot e, se TELEGRAM_CHAT_ID existir, envia uma mensagem de teste."""
    if not os.environ.get("TELEGRAM_TOKEN"):
        print("Falta a variável TELEGRAM_TOKEN (o token do @BotFather).")
        return
    eu = _chamar(sessao, "getMe")
    print(f"Bot: @{eu['username']}")
    chats = {}
    for u in _chamar(sessao, "getUpdates"):
        msg = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        c = msg.get("chat")
        if c:
            chats[c["id"]] = c.get("title") or " ".join(filter(None, [c.get("first_name"), c.get("last_name")])) or c.get("username")
    if chats:
        print("Chats encontrados (usa o número como TELEGRAM_CHAT_ID):")
        for i, nome in chats.items():
            print(f"  {i}  {nome}")
    else:
        print(f"Nenhum chat ainda. Abre o Telegram, procura @{eu['username']}, carrega em Iniciar, envia 'olá' e repete.")
    if os.environ.get("TELEGRAM_CHAT_ID"):
        print("Mensagem de teste enviada." if enviar(sessao, ["✅ Caçador de Oportunidades ligado. Os alertas vão chegar aqui."])
              else "Falhou o envio de teste: confirma o TELEGRAM_CHAT_ID.")

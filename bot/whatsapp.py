"""Alertas no WhatsApp através do CallMeBot (opcional; gratuito, só envia para o próprio número).

  WHATSAPP_TELEFONE  ex.: +351912345678
  WHATSAPP_APIKEY    a chave que o CallMeBot envia por WhatsApp
"""
import logging
import os
import time

API = "https://api.callmebot.com/whatsapp.php"
log = logging.getLogger(__name__)


def configurado() -> bool:
    return bool(os.environ.get("WHATSAPP_TELEFONE") and os.environ.get("WHATSAPP_APIKEY"))


def enviar(sessao, mensagens: list) -> bool:
    ok = True
    for i, m in enumerate(mensagens):
        if i:
            time.sleep(4)  # o CallMeBot limita o ritmo de envio
        try:
            r = sessao.get(API, params={"phone": os.environ["WHATSAPP_TELEFONE"], "text": m,
                                        "apikey": os.environ["WHATSAPP_APIKEY"]}, timeout=30)
            if r.status_code != 200:
                log.warning("CallMeBot respondeu %s", r.status_code)
                ok = False
        except Exception as e:
            log.warning("Falha a enviar WhatsApp: %s", e)
            ok = False
    return ok

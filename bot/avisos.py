"""Texto dos alertas e envio para todos os canais configurados (Telegram e/ou WhatsApp)."""
import html
import logging

log = logging.getLogger(__name__)
ICONE = {"mota": "🏍️", "carro": "🚗", "casa": "🏠", "terreno": "🌳"}


def euros(v):
    return f"{round(v):,}".replace(",", " ") + " €"


def _valor(v, unidade):
    return f"{v:.0f} €/m²" if unidade == "€/m²" else euros(v)


class Formato:
    """Telegram usa HTML (<b>, links); WhatsApp usa *negrito* e texto simples."""
    def __init__(self, nome):
        self.html = nome == "telegram"

    def t(self, s):
        return html.escape(str(s or ""), quote=False) if self.html else str(s or "")

    def negrito(self, s):
        return f"<b>{self.t(s)}</b>" if self.html else f"*{s}*"

    def ligacao(self, url, texto="Abrir anúncio"):
        if not url:
            return ""
        return f'<a href="{html.escape(url)}">{self.t(texto)}</a>' if self.html else url


def bloco(a: dict, f: Formato) -> str:
    linhas = [f.t(f"{ICONE.get(a['tipo'], '🔎')} {a['procura']}"), f.negrito(a["titulo"])]
    preco = f"{euros(a['preco'])}  (−{round(a['desconto'] * 100)}%, normal {_valor(a['mediana'], a['unidade'])})"
    if a.get("preco_antes"):
        preco += f"  ⬇ baixou de {euros(a['preco_antes'])}"
    linhas.append(f.t(preco))
    if a.get("problemas"):
        linhas.append(f.t("⚠ " + ", ".join(a["problemas"])))
    if a.get("sinais"):
        linhas.append(f.t("⏱ Pressa: " + ", ".join(a["sinais"])))
    local = a.get("local") or ""
    if a.get("km") is not None:
        local += f" (a {a['km']} km)"
    linhas.append(f.t(f"{local} — {a['fonte']}".strip(" —")))
    linhas.append(f.ligacao(a.get("url")))
    return "\n".join(l for l in linhas if l)


def montar_mensagens(boas: list, rever: list, canal: str = "whatsapp", limite: int = 1500) -> list:
    f = Formato(canal)
    partes = []
    if boas:
        partes.append("🎯 " + f.negrito("Boas compras"))
        partes += [bloco(a, f) for a in sorted(boas, key=lambda a: -a["desconto"])]
    if rever:
        partes.append("🔧 " + f.negrito("A rever (com problemas)"))
        partes += [bloco(a, f) for a in sorted(rever, key=lambda a: -a["desconto"])]
    mensagens, atual = [], ""
    for p in partes:
        if atual and len(atual) + len(p) + 2 > limite:
            mensagens.append(atual)
            atual = ""
        atual = f"{atual}\n\n{p}" if atual else p
    if atual:
        mensagens.append(atual)
    return mensagens


def enviar_todos(sessao, boas: list, rever: list, so_mostrar: bool = False):
    """Envia para cada canal configurado. Sem canais (ou com so_mostrar), escreve no ecrã."""
    from . import telegram, whatsapp
    canais = [("telegram", telegram, 3800), ("whatsapp", whatsapp, 1500)]
    configurados = [(n, m, lim) for n, m, lim in canais if m.configurado()]
    if not boas and not rever:
        return
    if so_mostrar or not configurados:
        if not so_mostrar:
            log.warning("Nenhum canal de alertas configurado (TELEGRAM_* ou WHATSAPP_*). Alertas:")
        print("\n---\n".join(montar_mensagens(boas, rever, "whatsapp")))
        return
    for nome, modulo, limite in configurados:
        modulo.enviar(sessao, montar_mensagens(boas, rever, nome, limite))

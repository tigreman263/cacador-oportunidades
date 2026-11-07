"""Fontes de anúncios. Cada fonte devolve dicionários no formato comum:

  id, fonte, titulo, descricao, preco, area, url, cidade, distrito, lat, lon (e, opcional, publicado)
"""
from . import autouncle, custojusto, drive

FONTES = {"custojusto": custojusto.procurar, "autouncle": autouncle.procurar,
          "drive": drive.procurar}

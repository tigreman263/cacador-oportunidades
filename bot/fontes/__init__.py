"""Fontes de anúncios. Cada fonte devolve dicionários no formato comum:

  id, fonte, titulo, descricao, preco, area, url, cidade, distrito, lat, lon
"""
from . import autouncle, custojusto

FONTES = {"custojusto": custojusto.procurar, "autouncle": autouncle.procurar}

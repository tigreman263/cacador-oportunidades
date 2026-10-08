from . import custojusto, olx

# Para acrescentar uma fonte nova (ex.: Standvirtual), cria o ficheiro
# com uma função procurar(sessao, procura) e regista-a aqui.
FONTES = {
    "olx": olx.procurar,
    "custojusto": custojusto.procurar,
}

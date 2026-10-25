"""Libreria di audit del gold pilota contro lo snapshot Neo4j.

I moduli puri (normalize, aliases, compare, classify, serialize, gold) non importano
nulla di pesante: sono eseguibili senza Neo4j e senza client LLM. Solo `graph_client`
tocca il driver, e lo fa con import differito dentro il metodo.
"""

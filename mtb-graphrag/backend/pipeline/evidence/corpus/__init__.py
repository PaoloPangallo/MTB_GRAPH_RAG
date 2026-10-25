"""Namespace del corpus V3 prototipale promosso.

Il package esiste per tenere separate due cose che finora coincidevano: il
repository shadow, che e' un artefatto di valutazione sotto `benchmarks/`, e un
corpus *promosso*, che e' un contenuto versionato con un registro proprio.

La separazione non e' organizzativa. Il percorso operativo — retriever,
scoring, adapter — non importa nulla da qui, e questo package non importa nulla
da quel percorso: un corpus promosso che diventasse raggiungibile dal retriever
per il solo fatto di esistere renderebbe indistinguibile "promosso per il
prototipo" da "in uso", che e' la distinzione che questa fase deve mantenere.
"""

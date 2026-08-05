# Configurazione provider

L'interfaccia è provider-agnostic. Il provider reale è un adapter Ollama che
riusa la costruzione esistente del repository. Sono registrati provider,
modello, versione, endpoint, temperatura, seed, top-p, limiti, timeout, prompt
e schema version, run index, timestamp, token, latenza, retry e raw-response
hash.

Temperatura richiesta: 0 o il minimo supportato. Nessuna API key è salvata nei
file. In questa esecuzione il provider non è configurato e non effettua
chiamate.

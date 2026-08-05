# Smoke test reale Minimax

Modello: minimax-m3:cloud
Endpoint: ollama Python client, ollama.chat
Chiamate: 3
SourceUnit per bundle: 4
Testo documentale inviato: 8.878 caratteri, circa 1.266 parole
Articoli completi/PDF locali: non inviati

Bundle:

- EB-b4c48ba003913f278ff182a6 — baseline DIRECT
- EB-2ae853e8abf1195cc4c84846 — baseline PARTIAL
- EB-6a291f12975b20b79e1c3dd7 — baseline CONTRADICTED

Risultato:

- JSON validi: 0/3
- REJECTED_SCHEMA: 3/3
- campi accettati: 0
- campi scartati: 0
- citazioni inesistenti accettate: 0
- SourceUnit inventate accettate: 0
- negazioni perse: non valutabile perché le risposte non sono parseabili
- contraddizioni perse: non valutabile perché le risposte non sono parseabili
- token input riportati: 5.305
- token output riportati: 3.072
- latenza totale: 26.241,882 ms
- latenza media: 8.747,294 ms

Il modello ha raggiunto l'endpoint, ma non ha prodotto JSON conforme al
protocollo. Il pilot completo è fermato secondo hard stop.

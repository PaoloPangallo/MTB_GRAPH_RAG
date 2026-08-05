# Limiti del pilot

## Conteggio onesto delle chiamate reali nella sessione

Il file `pilot_metrics.json` riporta le chiamate della run finale (7,
tutte enricher, dato che i 5 parser sono stati riusati da una run
precedente). Il conteggio reale delle chiamate fatte in questa sessione,
incluse quelle di run intermedie interrotte da bug nel codice
deterministico (non nel modello), è:

1. Prima run: 5 chiamate parser (tutte valide) — fermata da un bug nel
   Match Verifier (offset autoriportati trattati come autorevoli anziché
   solo come disambiguatore), corretto senza richiamare il modello.
2. Seconda run (parser riusato dalla cache): 5 chiamate enricher — la
   retrieval trovava solo 3 associazioni su 4 attese per un secondo bug
   (matching del biomarcatore limitato al solo campo `gene`), corretto
   senza richiamare né il parser né il modello per le run successive.
3. Terza run (finale, parser riusato): 7 chiamate enricher con retrieval
   corretta.

**Totale chiamate reali nella sessione: 17 su 20 autorizzate.** Nessuna di
queste è stata una "chiamata semantica ripetuta" nel senso vietato dal
protocollo (mai richiamato per astensione, rigetto, direzione errata o
esito diverso dalla baseline) — tutte le richiamate sono state conseguenza
di bug fix nel codice deterministico a monte del modello (verificatore e
retrieval), non di insoddisfazione per l'output del modello. Le chiamate
del secondo giro (5, con retrieval ancora buggata) sono comunque chiamate
reali già spese e non recuperabili; il budget rimanente dopo questa
sessione è 3/20.

## Nessun ENRICHMENT_ACCEPTED in questa run

Le 4 chiamate a trasporto valido si sono tutte astenute correttamente
(vedi `paper_context_enricher.md`); le altre 3 sono fallite per un
problema di conformità allo schema (`EVIDENCE_KIND_INVALID`), non di
grounding. Questo significa che il pilot non dimostra un esempio positivo
di citazione validata end-to-end in questa run specifica — ma dimostra
con forza le proprietà di sicurezza (nessuna fabbricazione, corretto
riconoscimento di BGJ398≠infigratinib nel Caso 4). Non è stato tentato
alcun nuovo tentativo per ottenere un esempio positivo, per rispetto del
divieto di retry semantico.

## Selezione dei casi non indipendente dal ricercatore

I 5 casi sono stati scelti a mano da chi ha eseguito il pilot (non
campionati casualmente) per coprire deliberatamente i pattern richiesti
dal protocollo — introduce un bias di selezione verso casi "istruttivi",
non rappresentativo della distribuzione naturale dei 25 EvidenceBundle.

## Validazione del riassunto è euristica

Il controllo "summary non contiene fatti assenti dalla quote"
(`enrichment_validator.py`) usa un rapporto di sovrapposizione lessicale
tra parole di contenuto (soglia 25%/50%), non un controllo semantico
completo — può in teoria accettare un riassunto lessicalmente simile ma
semanticamente distorto, o rigettarne uno corretto ma parafrasato in modo
molto diverso. In questa run non è mai stato esercitato (0 riassunti
raggiunti la validazione).

## Cache documenti riusata invariata

Nessun nuovo documento recuperato; la cache è la stessa popolata durante
lo Stadio 1 del Claim Extractor.

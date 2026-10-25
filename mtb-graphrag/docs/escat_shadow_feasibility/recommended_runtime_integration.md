# Raccomandazione per integrazione futura

## Decisione

**D. MANUAL CURATION**

Il sistema può produrre una scheda shadow incompleta per revisione umana, ma
non deve assegnare tier nel runtime attuale. La scelta è prudenziale perché:

- la fonte normativa ESCAT non è verificata localmente;
- nessuna claim attiva contiene un'annotazione ESCAT esplicita;
- solo 17 claim hanno testo, locator e fonte locali;
- il legacy usa LLM e mapping generici;
- study design, outcome e approvazione non sono disponibili nella matrice.

## Superficie futura

Una futura sezione separata del dossier, “Actionability clinica”, dovrebbe
mostrare framework, versione, tier, subtier, origine, fonte, campi mancanti,
confidence, data assessment e stato.

Deve distinguere visivamente:

- ESCAT esplicito;
- ESCAT derivato da regola versionata;
- ESCAT da revisione manuale;
- ESCAT non assegnabile.

## Gate di sicurezza

Il modulo non deve modificare gate, score, bucket, ordine o ammissione. Un
assessment shadow non è un valore di case relevance e non sostituisce
provenance o document support.

Prima di qualunque integrazione servono:

1. fonte ESCAT primaria verificata e versionata;
2. registry delle regole con rule_id e test;
3. supporting passage e locator;
4. gestione esplicita di contesto, outcome e studio;
5. revisione manuale indipendente;
6. confronto read-only con V3 invariata.

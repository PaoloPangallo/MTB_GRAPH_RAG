# Esclusioni della logica legacy

`backend/pipeline/agents/variant_interpreter.py` è stato analizzato solo per
confronto. Usa prompt LLM e fallback euristici su tumor matching, livelli
generici e tipo di alterazione; non dispone di una regola ESCAT locale
versionata con provenance. Il valore `escat_tier` legacy è quindi soltanto
`UNVERIFIED_LEGACY_DERIVATION`.

Il MVP vieta esplicitamente:

- import del tier legacy;
- mapping `evidence_level` A/B/C/D verso ESCAT;
- assegnazione da solo PMID, keyword di malattia o output LLM;
- tier senza `rule_id`, framework version e fonte normativa;
- uso del tier per gate, score, bucket o ordinamento.

Le categorie storiche sono riportabili solo in un confronto informativo e
non sono ground truth.

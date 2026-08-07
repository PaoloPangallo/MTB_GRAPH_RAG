# 05 — Narrative Verifier

`narrative-verifier/1.0` · `backend/research_pipeline/narrative/verifier.py`
Lexicon: `narrative-lexicon/1.0`

Riceve `canonical_dossier`, `narrator_input`, `narrative_output`.
**Nessun LLM. Nessuna rete. Nessun retrieval. Nessuna query al KG.**
Un test lo verifica staticamente: il modulo non contiene i simboli `requests`,
`transport`, `llm_config`, `ollama`, `call_narrator`.

## Sei famiglie di controllo

| § | Controllo | Reason code |
|---|---|---|
| 10 | entity closure | `NARRATIVE_UNAUTHORIZED_ENTITY` |
| 11 | status preservation | `NARRATIVE_STATUS_ESCALATION` |
| 12 | polarity preservation | `NARRATIVE_POLARITY_INVERSION` · `NARRATIVE_NEGATION_LOST` |
| 13 | quote e provenance | `NARRATIVE_UNAUTHORIZED_QUOTE` · `NARRATIVE_REJECTED_QUOTE_PROMOTED` |
| 14 | recommendation | `NARRATIVE_UNAUTHORIZED_RECOMMENDATION` |
| 15 | omissioni critiche | `NARRATIVE_CRITICAL_LIMITATION_OMITTED` |

Più `NARRATIVE_UNKNOWN_CANDIDATE_ID` e `NARRATIVE_MISSING_CANDIDATE`.

## §10 Entity closure

L'insieme autorizzato è costruito **solo** dal NarratorInput. Tre rilevatori:

- **identificatori** — `PMID:…`, `NCT…`, DOI: forme canoniche, non qualunque
  numero;
- **simboli maiuscoli** — geni e farmaci scritti come nel dossier. Il limite di
  7 caratteri della prima versione lasciava passare `PEMBROLIZUMAB` ed è stato
  rimosso;
- **radici INN** — `-mab`, `-nib`, `-tinib`, `-parib`, `-platin`… Regola
  **morfologica**, non un elenco di farmaci: un elenco sarebbe sempre incompleto
  e andrebbe mantenuto, mentre le radici INN sono assegnate dall'OMS per classe.
  Intercetta un farmaco inventato anche in minuscolo, dove la regola sui simboli
  maiuscoli non arriva.

## §11 Status preservation

Il controllo è **asimmetrico**: le affermazioni di supporto stabilito vengono
cercate soltanto per le candidate il cui dossier **non** esprime supporto
(`expresses_support = false`). Ciò che il dossier afferma resta dicibile: una
candidate `DIRECT` può essere descritta come supportata.

## §12 Polarity preservation

Per `SOURCE_DOES_NOT_SUPPORT` e `CONTRADICTED` servono due condizioni: nessuna
affermazione di supporto **e** presenza di un marcatore di negazione esplicito.
Una narrativa che semplicemente tace la negazione fallisce con
`NARRATIVE_NEGATION_LOST`.

## §13 Quote

Vengono estratte le stringhe fra virgolette di almeno 25 caratteri: una
citazione breve non è una citazione. Ogni quote deve appartenere alle
`validated_quotes`. Una quote che coincide con una **rigettata** produce il
reason code dedicato `NARRATIVE_REJECTED_QUOTE_PROMOTED`, distinto
dall'invenzione pura: sono due difetti diversi e il report deve distinguerli.

## §14 Recommendation

Il dossier canonico non contiene alcuna recommendation clinica — verificato in
`00_current_dossier_contract.md`. Qualunque formulazione prescrittiva è quindi
non autorizzata, senza eccezioni da modellare. Coperte 12 forme inglesi e 12
italiane.

## §15 Omissioni critiche

Solo i warning dichiarati `NARRATIVE_CRITICAL`. Tre controlli: ambiguità non
dichiarata, citazione validata assente non dichiarata, `Does Not Support` non
dichiarato.

## Normalizzazione Unicode

Il lexicon applica **NFC** a pattern e testo. In italiano la lettera accentata
può arrivare precomposta (U+00E8) oppure come lettera più accento combinante
(U+0300): sono la stessa lettera per un lettore e due stringhe diverse per una
regex. Senza NFC un modello che usasse la seconda forma avrebbe aggirato
l'intera policy scrivendo una frase indistinguibile a occhio nudo.

Il difetto è emerso **dai test**, non dalla lettura del codice.

## Determinismo

`result_fingerprint()` esclude i soli campi temporali. Stessa coppia (dossier,
narrativa) produce la stessa impronta e gli stessi reason code, verificato sia
sul PASS sia sul FAIL.

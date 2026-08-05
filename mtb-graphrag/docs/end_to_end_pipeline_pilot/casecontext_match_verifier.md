# CaseContext Match Verifier

Interamente deterministico, nessun LLM (nessuna auto-conferma del parser
sul proprio output, per istruzione esplicita). Per ogni campo controlla
presenza letterale della quote nel testo, disambiguazione tramite offset
solo in caso di occorrenze multiple, e coerenza tra `normalized_value` e
quote.

## Bug reale trovato e corretto durante il pilot

Prima versione: trattava gli offset autoriportati dal modello come
autorevoli, rigettando come `MISMATCH` (`OFFSET_TEXT_MISMATCH`) quote
letteralmente corrette ma con offset sbagliati di pochi caratteri —
bloccava tutti e 5 i casi con esito `CASECONTEXT_MISMATCH` prima ancora
del retrieval, nonostante le estrazioni fossero corrette. Corretto
trattando la presenza letterale della quote come autorevole; gli offset
autoriportati sono usati solo per scegliere tra occorrenze multiple. Test
di regressione:
`MatchVerifierTests.test_slightly_wrong_offsets_do_not_override_a_confirmed_unambiguous_quote`.

## Risultati finali (25 campi controllati su 5 casi)

| Esito | Conteggio |
|---|---:|
| MATCH | 25 |
| MISMATCH | 0 |
| UNCERTAIN | 0 |
| MISSING_IN_TEXT | 5 |

Nessun MISMATCH essenziale ha raggiunto il retrieval in nessun caso — il
Caso 5 (biomarker fabbricato) produce correttamente `MATCH` sul campo
biomarker (il gene fabbricato è genuinamente presente nel testo, il
parser lo ha estratto fedelmente) mentre il blocco avviene un passo dopo,
al retrieval (nessuna candidate compatibile nel KG) — coerente con
l'obiettivo del Caso 5 dichiarato in `case_definitions.py`.

# MVP compliance report

## Discrepanze rilevate

La verifica di `fe01fd1` ha rilevato che la documentazione dichiarava due
claim diagnostiche `NOT_APPLICABLE`, mentre il dataset reale delle 15 claim
`PARTIALLY_ASSIGNABLE` conteneva soltanto claim terapeutiche. La CLI inoltre
non implementava tutte le operazioni documentate, `export_dossier()` forzava
`INCOMPLETE` in assenza di tier e la validazione non controllava rule id,
versione, condizioni o requisiti del subtier.

## Causa

Il commit precedente aveva implementato il modello minimo e un sottoinsieme
dei comandi, ma non aveva sincronizzato i conteggi documentali con il pilota
n? completato il workflow mutabile e la validazione strutturale.

## Correzioni applicate

- documentazione e summary allineati a 15 terapeutiche, 0 diagnostiche,
  15 `INCOMPLETE`, 0 `NOT_APPLICABLE`;
- CLI completata con show-draft, edit-field, curator, rationale, status,
  reject, supersede, export-dossier e audit per ogni operazione;
- transizioni di stato esplicite e tentativi invalidi registrati senza
  corrompere il record;
- supersessione con snapshot del precedente assessment;
- export read-only con stato preservato;
- validazione strutturale di rule id, framework/version, fonte regola,
  source distinta, campi, condizioni, esclusioni, alternative e subtier;
- fixture tecnica marcata `TEST_FIXTURE_ONLY` e
  `NOT_AN_OFFICIAL_ESCAT_RULESET`.

## Test

`python -m unittest discover -s benchmarks/mtb_evidence/escat_curation_mvp/tests -v`
verifica 18 test superati. I test includono pilota, CLI, audit, transizioni,
export e rule set sintetico. Nessun test presenta la fixture come fonte
ufficiale.

## Stato finale e limiti

Il rule set ESCAT ufficiale locale ? ancora assente. Nessuna curazione ESCAT
scientifica ? stata effettuata e nessuna integrazione ? stata fatta nel
runtime V3, nei bucket, nello scoring o nel gate. La fixture dimostra soltanto
che la validazione tecnica ? predisposta a ricevere in futuro un rule set
versionato e documentato.

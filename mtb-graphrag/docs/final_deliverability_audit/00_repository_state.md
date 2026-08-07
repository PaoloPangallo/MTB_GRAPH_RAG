# 00 — Stato del repository

Dati: `evaluation/final_deliverability/repository_state.json`.

| | |
|---|---|
| Branch | `fix/pre-freeze-deliverability-blockers` |
| HEAD | `e25a63b77848a30d3b7249b1d8c2b6339cd6e6af` |
| Base commit | `0219e0a7a4a063668c72c941413fbd8382838b32` |
| Commit del fix sprint | **11** |
| Working tree | pulita da modifiche al codice |
| `code_modified_during_final_audit` | **false** |

## Working tree

Untracked: i **12 path già autorizzati** nelle fasi precedenti (PDF/TeX di
relazione, `architettura/README.md`, `Mateo.pdf`, gli artifact esploratori
`manual_v3_cases*`, `scripts/start_v3_product.ps1`), più la directory
`evaluation/final_deliverability/` creata da questo audit.

**Nessun file `.py`, `.tsx` o `.ts` modificato o non committato.** Il codice
auditato è esattamente quello di `e25a63b`.

## Superficie del fix sprint

**7 file applicativi** modificati rispetto a `0219e0a`:

```
backend/research_pipeline/determinism/gates.py     ISS-002
backend/research_pipeline/contracts.py             ISS-001
backend/research_pipeline/orchestrator.py          ISS-003
backend/research_pipeline/dossier/builder.py       ISS-003
frontend/src/research/DossierView.tsx              ISS-003
frontend/src/research/stages/EligibilityStage.tsx  ISS-004
backend/config/requirements.txt                    ISS-006
```

più `README.md`, 3 file di test nuovi, 1 script di evaluation nuovo
(`run_rq4_canonical_runtime.py`) e 3 file di configurazione
(`pytest.ini`, `requirements-dev.txt`, `requirements-lock.txt`).

## Artifact storici — invariati

```
$ git diff --name-only 0219e0a..HEAD -- evaluation/rq1_* evaluation/rq2_* \
    evaluation/rq3_* evaluation/rq4_* evaluation/gca_v3 \
    evaluation/runtime_v3_integration evaluation/gold benchmarks gca_v3
(nessuna riga)
```

**Una nota di metodo.** Il confronto per hash SHA-256 fra il file su disco e il
blob di `0219e0a` mostrava quattro file «diversi»:
`rq1/kg_source_fingerprint.json`, `rq2/aggregate_metrics.json`,
`rq4/aggregate_metrics.json`, `runtime_v3_integration/eligibility_metrics.json`.

Verificato normalizzando i fine riga: la differenza è **esclusivamente**
CRLF sul disco contro LF nel blob — artefatto preesistente del checkout su
Windows, non una modifica. Il contenuto è identico e git non registra alcuna
variazione. È il tipo di falso positivo che un audit deve distinguere da un
reperto reale.

Gli artifact delle due fasi precedenti (`evaluation/deliverability/`,
`docs/deliverability_audit/`, `evaluation/pre_freeze/`,
`docs/pre_freeze_fixes/`) sono presenti e non sono stati toccati.

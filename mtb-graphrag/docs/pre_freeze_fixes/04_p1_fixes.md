# 04 — P1

Dati: `evaluation/pre_freeze/p1_regression_results.json`,
`evaluation/pre_freeze/frontend_build_result.json`.

Corretti i tre P1 con `blocks_freeze = TRUE`. ISS-007 è P1 ma
`blocks_freeze = FALSE` ed è fuori perimetro: vedi sotto.

---

## ISS-004 · Build del frontend — CHIUSO

**Riprodotto prima del fix:**

```
$ npx tsc -b --force
src/research/stages/EligibilityStage.tsx(83,8):  error TS2769
… (110, 126, 151, 186, 202)
exit=2
```

`@mui/material@9.0.1` non accetta più `alignItems` e `flexWrap` come prop
dirette di `Stack`. `tsc -b` esce con 2 e **`vite build` non viene mai
raggiunto**. Non è deriva di dipendenze: `package-lock.json` è tracciato e la
versione installata è esattamente 9.0.1.

**Correzione:** le prop spostate in `sx`, che produce le identiche regole CSS.

```diff
- <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
+ <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
```

Nessun `any`, nessun `@ts-ignore`, nessun typecheck disabilitato, nessun
comportamento applicativo modificato — come richiesto dal §16.

Corretto anche un `TS18048` che i test aggiunti in questo branch avevano
introdotto (`candidate_therapies` è opzionale nel tipo `Dossier`).

```
npm run build   exit 2  ->  exit 0
                vite build completato, dist/assets/index-*.js 2 243,70 kB
vitest          200 passed (195 preesistenti + 5 nuovi)
```

---

## ISS-005 · RQ4 bypassava l'orchestratore — CHIUSO

`run_runtime_v3_integration.rq4_rerun` dichiara nel proprio codice:

> `# Nessuno stage downstream è raggiungibile da questo harness: non li importa.`

Nuovo script `evaluation/run_rq4_canonical_runtime.py`: gli stessi 35 casi
attraverso `orchestrator.run_case`. Dettaglio in `02_eligibility_stop_fix.md`.

**Il §8 chiedeva di non riscrivere i risultati storici**: non sono stati
toccati. L'output va in `evaluation/rq4_canonical_runtime/`, e le due modalità
sono etichettate esplicitamente (`evaluation_path`, `compared_against`) in ogni
riga e nel sommario. I due percorsi risultano **equivalenti**
(`path_disagreements = 0`), e questo è documentato invece che dato per scontato.

---

## ISS-006 · Ambiente non riproducibile — CHIUSO

**Riprodotto prima del fix:** `requirements.txt` dichiarava 10 pacchetti senza
alcuna versione a fronte di 188 installati, e non conteneva `pytest`, `httpx`,
`pandas` né `numpy`. Nessun `pytest.ini`, `conftest.py` o `pyproject.toml`:
`pytest` dalla radice falliva con `ModuleNotFoundError: backend`.

**Correzione — quattro file:**

| File | Contenuto |
|---|---|
| `backend/config/requirements.txt` | versioni vincolate al minore installato e verificato |
| `backend/config/requirements-dev.txt` | `pytest`, `httpx`, `pandas`, `numpy` — senza questi le suite non partono |
| `backend/config/requirements-lock.txt` | `pip freeze` dell'ambiente esatto di questa fase (193 righe) |
| `pytest.ini` | `pythonpath = .` e `testpaths` delle tre suite |

**Verifica con `PYTHONPATH` rimosso dall'ambiente:**

```
$ env -u PYTHONPATH pytest
3189 passed, 17 skipped, 36890 subtests passed in 192.31s
```

Prima dello stesso comando: `ModuleNotFoundError`.

Il README è stato aggiornato: dichiara esplicitamente che
`requirements.txt` da solo non basta a far girare i test.

---

## ISS-007 · Denominatore end-to-end — NON AFFRONTATO

P1 ma `blocks_freeze = FALSE`. È una correzione di **presentazione nelle tabelle
della tesi** — affiancare il denominatore end-to-end (16 candidate raggiungibili)
a quello di popolazione (46 864) — non una modifica al codice o agli artifact.
Fuori dal perimetro del §15, che limita questa fase ai P1 bloccanti.

Resta in `evaluation/pre_freeze/remaining_issues.csv` come `OPEN`.

---

## ISS-017 · Non corretto, come previsto dal §17

Il §17 chiedeva di consultare la severità reale in `issues.csv`: è **P3**,
`blocks_freeze = FALSE`. Non corretto in questo branch.

La prescrizione «in ogni caso non sovrascrivere artifact storici durante i test»
è stata rispettata: `run_rq1` e `run_gca_v3_audit` **non sono stati rieseguiti**.
La regressione RQ1/RQ2 è stata verificata per chiusura transitiva degli import
(vedi `05_regression_results.md`), che è più forte di una riesecuzione e non
comporta alcun rischio di scrittura.

# 07 — Limiti residui

Elenco completo: `evaluation/final_deliverability/remaining_issues.csv`.

```
P0                        0
P1 bloccanti              0
P1 non bloccanti          1   ISS-007
P2                        9   (8 preesistenti + NEW-01)
P3                        8   (6 preesistenti + NEW-02, NEW-03)
nuovi P0                  0
```

## I tre rilievi nuovi di questo audit

### NEW-01 · `THERAPY_DISCOVERY` non segnala la polarità — **P2**

`evaluate_association` ritorna per il ramo discovery prima del controllo di
polarità. Una candidate con fonte `Does Not Support` riceve
`DISCOVERED / DISCOVERY_BUCKET`, `direction = NOT_APPLICABLE`, **nessun
warning**.

Non viola i criteri del §17 e non è promozione a supporto. È però un'assenza di
segnale: 999 candidate nel repository, **1 sola** raggiungibile end-to-end.

Da dichiarare nella tesi. Non da correggere prima del freeze.

### NEW-02 · `npm run lint` fallisce — **P3**

36 errori in 9 file, **tutti preesistenti a `0219e0a`** e nessuno toccato dal
fix sprint. Categoria `react-refresh/only-export-components`: ergonomia di
sviluppo, non correttezza. Non è fra i criteri di freeze.

### NEW-03 · Polarità non mappata → `UNKNOWN` — **P3**

Una stringa di polarità non riconosciuta in `evidence_direction` ricade su
`UNKNOWN` invece di essere rifiutata. Teorico: i valori reali sono solo
`Supports`, `Does Not Support`, stringa vuota o assente. Nessuna candidate reale
è affetta.

## ISS-007 — P1 non bloccante, correttamente documentato

Il §11 chiede di verificare **solo** che la distinzione fra i due denominatori
sia documentata. Lo è, esplicitamente, in
`docs/pre_freeze_fixes/07_remaining_limits.md` e `06_rq_impact.md`:

```
FULL-CORPUS DENOMINATOR        46 864 candidate
END-TO-END RUNTIME DENOMINATOR      16 candidate
```

I report finali non confondono i due. **Non è quindi nemmeno un blocker
documentale.** Resta da applicare alle tabelle della tesi.

## I limiti che restano proprietà del runtime

Da dichiarare, perché non sono stati corretti per scelta di perimetro:

- **il contratto 2.0 non rappresenta alterazioni composte né regimi**:
  `A AND B` corrisponde ancora a un caso che menziona solo `A`, e
  `KRAS G12D` corrisponde a `KRAS G12C`. Correggerlo significherebbe migrare a
  GCA v3, esplicitamente fuori perimetro;
- **LIVE non è eseguibile senza `data_cache/`**, quindi la validazione delle
  quote end-to-end resta dimostrata a livello di componente e su artifact
  congelati;
- **in REPLAY la validazione è rigiocata, non rieseguita** (`replay.py:117-132`);
- **16 candidate su 46 864** sono raggiungibili end-to-end;
- **il parser fallisce il trasporto nel ~26 %** dei casi del benchmark;
- **narrator e narrative verifier non sono implementati**: ciò che l'MTB vede è
  il dossier strutturato reso dalla UI.

Nessuno di questi è un difetto emerso oggi: sono tutti già documentati, e
nessuno viola i criteri di freeze.

# 08 — Integrazione nella UI

## L'API espone due viste separate

`GET /runs/{id}/dossier`

```jsonc
{
  "dossier": { … },                    // vista CANONICA, invariata
  "narrative": { … } | null,           // popolata SOLO se il verifier ha accettato
  "presentation_mode": "VERIFIED_NARRATIVE" | "STRUCTURED_DOSSIER_FALLBACK",
  "narrative_verification": {
    "status", "reason_codes", "verifier_version", "narrative_hash", "input_hash"
  }
}
```

`narrative` è `null` quando la verifica fallisce. Il client non riceve una
narrativa che non deve mostrare.

## Il frontend non decide

```tsx
function isValidatedAuthorClaim(e) { return e.presentation_state === 'VALIDATED_QUOTE'; }
const verified = presentationMode === 'VERIFIED_NARRATIVE' && narrative != null;
```

È la stessa regola che ha chiuso ISS-003 per le quote: **la fonte
dell'accettazione sta nel backend, mai in un'inferenza del client**. Un test
verifica il caso limite più insidioso — un payload narrativo presente ma con
`presentation_mode = STRUCTURED_DOSSIER_FALLBACK` non viene mostrato.

Il frontend non calcola status, non deduce validazione, non ordina candidate per
supporto.

## Le due sezioni

**`DOSSIER STRUCTURED`** — invariato. Evidenza deterministica, author context
(con la sezione «PROPOSTE NON VALIDATE — SOLO AUDIT» introdotta da ISS-003),
limitazioni.

**`VERIFIED NARRATIVE`** — nuovo. Chip di stato, sintesi, una sezione per
candidate, limitazioni, nota di chiusura, e in fondo versione del verifier e
hash della narrativa.

Quando la verifica fallisce, al posto della prosa compaiono i reason code e la
frase:

> «La narrativa non ha superato la verifica deterministica e non viene mostrata.
> Il dossier strutturato qui sopra resta completo e consultabile.»

Il dossier canonico non viene mai nascosto, in nessuno dei due stati.

## Dichiarazione permanente

Sopra la narrativa, sempre visibile:

> «Riformulazione leggibile di un dossier già deciso. Non modifica status, gate,
> support mask o provenance: il dossier strutturato resta la fonte canonica.»

## Test

6 test in `NarrativeView.test.tsx`: narrativa verificata mostrata; narrativa
fallita non mostrata; reason code al posto della prosa; narrativa assente;
**narrativa presente ma non verificata non promossa**; dichiarazione di non
modifica dello stato canonico presente.

`npm run build` → exit 0. Suite frontend: 206 test.

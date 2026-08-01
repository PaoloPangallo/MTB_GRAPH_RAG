# Diagnostica del bucket warning V3

## Esito

Il bucket warning non ? stato corretto: nei quattro casi il valore zero non dimostra un ramo irraggiungibile o un errore di gate. Il gate V3 assegna warning soltanto quando `final_bucket == WARNING_BUCKET`; gli oggetti tecnici, le associazioni e i risultati gi? demossi ad audit/rejected disabilitano la warning eligibility.

## Evidenza statica

- `integrated_gates_v13.py`: `warning = final_bucket == WARNING_BUCKET`.
- `integrated_gates_v13.py`: per bucket audit/rejected vengono impostati `primary = warning = False`.
- `structural_gates.py`: oggetti deprecated/audit-only sono demossi prima del ranking.
- I `warning_codes` vengono accumulati separatamente dal bucket finale, quindi un warning diagnostico non implica un elemento nel bucket warning.

## Casi esplorativi

| caso | warning | interpretazione |
|---|---:|---|
| 1 | 0 | corrispondenza diretta; i record non compatibili sono rejected o tecnici |
| 2 | 0 | direzione resistance preservata; nessun risultato warning |
| 3 | 0 | limitazioni rappresentate in audit/rejected, non warning |
| 4 | 0 | nessuna claim direttamente applicabile; astensione esplicita |

Non ? stata applicata alcuna correzione alla semantica dei gate.

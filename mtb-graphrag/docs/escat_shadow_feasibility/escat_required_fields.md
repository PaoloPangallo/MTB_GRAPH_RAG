# Requisiti dati per un assessment ESCAT

Questa matrice descrive la disponibilità locale per le 148 claim. La presenza
di biomarcatore, malattia e intervento non è sufficiente per assegnare un tier.

| requisito | fonte attesa | stato locale |
|---|---|---|
| biomarcatore/alterazione | claim o Evidence | 148 PRESENT_STRUCTURED |
| malattia | claim o fonte | 148 PRESENT_STRUCTURED |
| intervento | claim o fonte | 146 PRESENT_STRUCTURED; 2 NOT_APPLICABLE |
| direzione | claim | 148 PRESENT_STRUCTURED |
| relazione stesso/altro tumore | testo/source unit | 17 AMBIGUOUS; 131 MISSING |
| tipo evidenza | claim/source unit | 15 PRESENT_STRUCTURED; 131 MISSING; 2 NOT_APPLICABLE |
| study design | source unit/testo | 148 MISSING |
| prospettico/retrospettivo | source unit/testo | 148 MISSING |
| randomizzazione | source unit/testo | 148 MISSING |
| endpoint | source unit/testo | 148 MISSING |
| risposta clinica | source unit/testo | 148 MISSING |
| sopravvivenza | source unit/testo | 148 MISSING |
| preclinico | claim/source unit | 2 PRESENT_STRUCTURED; 146 MISSING |
| in vivo | source unit/testo | 148 MISSING |
| in vitro | source unit/testo | 148 MISSING |
| in silico | source unit/testo | 148 MISSING |
| approvazione/standard | fonte regolatoria o clinica | 148 MISSING |
| fonte e identifier | provenance | 17 PRESENT_STRUCTURED; 131 MISSING |
| source unit | source profile unit | 2 PRESENT_STRUCTURED; 15 PARENT_LEVEL_ONLY; 131 MISSING |
| locator | source unit/claim | 17 PRESENT_IN_LOCAL_TEXT; 131 MISSING |
| testo locale | passage reale | 17 PRESENT_IN_LOCAL_TEXT; 131 MISSING |
| framework version | assessment | 148 MISSING |
| rule source | framework registry | 148 MISSING |

PARENT_LEVEL_ONLY indica che l'identificatore è presente ma il record source
unit non è risolto nell'inventario attivo. Non equivale a testo disponibile.

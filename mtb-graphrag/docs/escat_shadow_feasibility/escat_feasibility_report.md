# Report di fattibilità ESCAT shadow

## Metodo

Sono state ispezionate le 148 claim attive, i 147 parent, le source profile
unit locali, i locator già presenti e gli asset del runtime legacy. La
classificazione è deterministica e conserva l'assenza come dato.

Non sono stati interrogati servizi live e non sono state ricostruite regole
ESCAT dalla memoria del modello.

## Risultati

- Tripla biomarcatore--malattia--intervento: 146/148 completa; le 2
  diagnostiche non hanno intervento per definizione del record.
- Fonte/identifier: 17/148.
- Locator: 17/148.
- Testo locale: 17/148.
- Study design: 0/148.
- Endpoint: 0/148.
- Outcome clinico: 0/148.
- Dati sufficienti per tier generale: 0/148, perché manca la fonte normativa
  versionata e mancano requisiti clinici.
- Partially assignable: 15/148, tutte terapeutiche con dati documentali
  locali ma senza regole ESCAT verificabili.
- Unassignable: 131/148.
- Not applicable: 2/148, le claim diagnostiche.
- Tier assegnati: 0.

I conteggi sono misure di disponibilità documentale e non accuratezza clinica.

## Pilota

Il pilota comprende 16 claim con EGFR L858R/NSCLC, ALK G1202R, FGFR2 fusion,
sensitivity, resistance, preclinical, aggregate, diagnostic, locator e casi
senza testo sufficiente. Per tutte:

- il tier shadow è null;
- lo stato è PARTIALLY_ASSIGNABLE, UNASSIGNABLE o NOT_APPLICABLE;
- la divergenza legacy è informativa e non ground truth;
- la mancanza della definizione ESCAT locale produce
  MISSING_FRAMEWORK_RULE.

## Claim assegnabili

Nessuna claim è ASSIGNABLE nel pilota. Le 15 parzialmente assegnabili hanno
campi claim, fonte, locator e testo locale, ma non possiedono una regola ESCAT
versionata né dati sufficienti per ricostruire in modo verificabile study
design, outcome e contesto.

## Rischi

- Il legacy può assegnare I-A/I-B da A/B generici.
- Il confronto disease è basato su substring e keyword.
- LLM e fallback producono un valore globale senza provenance di regola.
- II-A viene riscritto come II, perdendo granularità.
- Resistance viene forzata a non determinato senza una regola documentata.
- L'assenza di locator e testo impedisce di distinguere parent link da supporto
  claim-specifico.

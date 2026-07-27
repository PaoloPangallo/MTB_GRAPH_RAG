# Correzioni richieste prima della promozione: repository 1.4

Repository: `qualified_claim_repository/1.4`  
Modello: `qualified_claim_model/1.2`  
Stato: `shadow_not_promoted`  
Supera: `qualified_claim_repository/1.3`

La 1.4 non aggiunge, non toglie e non riscrive nessuna proposizione.
Applica quattro correzioni, ognuna legata a un finding dell'audit
pre-promozione, e nessuna delle quali tocca una decisione gia' presa.

## Conteggi

| Voce | Derivato | Atteso |
|---|---:|---:|
| `active_claims_total` | 148 | 148 |
| `aggregate_claims` | 3 | 3 |
| `atomic_claims` | 140 | 140 |
| `diagnostic_claims` | 2 | 2 |
| `parents` | 147 | 147 |
| `parents_without_claims` | 3 | 3 |
| `prognostic_claims` | 0 | 0 |
| `regimen_claims` | 3 | 3 |
| `therapeutic_claims` | 146 | 146 |
| `unresolved_associations` | 6 | 6 |
| `unsupported_associations` | 6 | 6 |

Conteggi invariati rispetto alla 1.3: **true**.
L'aggiunta della propagation policy non crea ne' elimina claim: e' un
campo di governance, non una proposizione.

## Propagation policy

| Policy | Claim |
|---|---:|
| `prototype_only` | 148 |

Claim con i tre campi obbligatori: **148/148**  
Schema uniforme: **true**  
Default impliciti in deserializzazione: false  
Record senza policy rifiutato: **true**

I sei claim che non dichiaravano la propria propagazione erano i tre
aggregati e i tre regimi, cioe' esattamente quelli la cui propagazione va
impedita. Il modello 1.1 aveva il campo su `AtomicInterventionClaim` e sui
non terapeutici, e non sugli altri due tipi: l'asimmetria non si vede
guardando i tipi uno per uno, e diventa un difetto quando i record
vengono serializzati insieme.

## Identita' dei claim

ID cambiati: **0**  
ID verificati: **148**  
Lineage richiesta: false

I campi di propagazione non appartengono alla formula di identita' e non
vi entrano ora. Il comportamento del gate non e' un campo del claim: un
ID che cambiasse perche' una forma si comporta diversamente al retrieval
direbbe che e' cambiata la proposizione, e non e' vero.

## Link plan

Azioni: **37**  
Schema: `qualification_link_plan/1.1`  
Significato cambiato: false  
Azioni eseguite: **0**

Le tre forme precedenti sono mappate su un solo schema di sette campi. I
campi legacy restano nell'artefatto della 1.3 e la mappa li registra,
cosi' che la normalizzazione sia leggibile invece di dover essere dedotta
dal codice che l'ha applicata.

Un dettaglio merita di essere detto perche' e' una deviazione dallo
schema richiesto: `source_unit_id` conserva il nome singolare e ha sempre
valore di lista. Un'azione ne porta legittimamente due — prima linea e
rechallenge dello stesso paziente — e sceglierne una sarebbe la perdita
silenziosa che questa normalizzazione esiste per impedire.

## Finding dell'audit pre-promozione

| Finding | Prima | Dopo | Esito |
|---|---|---|---|
| `CLAIM_IDENTITIES_STABLE` | `informational` | `none` | verified |
| `LINK_PLAN_SCHEMA_HETEROGENEOUS` | `minor` | `none` | resolved |
| `NO_DISTINCT_FORMULATION_OUTCOME` | `minor` | `none` | resolved |
| `PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS` | `major` | `none` | resolved |
| `SALT_FORM_CLAIMS_LEAVE_PRIMARY_BUCKET` | `none` | `informational` | accepted_and_recorded |
| `SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT` | `major` | `none` | resolved |
| `UNKNOWN_MODE_REJECTION_NOT_DECLARED` | `minor` | `none` | resolved |

## Integrita'

Artefatti congelati invariati: **true**  
Parita' della query operativa: **true**  
Record di gold letti: **0**  
Repository 1.3 modificato: false


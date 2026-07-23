# PMID:31358542 — revisione documentale

**Decisione strutturale: `audit_split_not_supported`**

la fonte non contiene evidenza preclinica. L'unica occorrenza di «in vitro» in tutto il full text sta in una frase che cita modelli di altri (riferimento 23). Nessuna linea cellulare, nessun xenograft, nessun IC50, nessuna trasfezione: lo split clinico/preclinico proposto dall'audit non ha oggetto

## 1-2. Fonte e disponibilita'

- PMID: `31358542` · PMC: `PMC6858956`
- Disponibilita': **full_text**
- Locator verificati: **5/5** ({'exact': 5})
- Hash del documento: `872ca747fedbef05628ed7b84094f144…`
- Full text conservato: **no**

## 3. Mappa clinico-preclinica

- Parte clinica: tutta la fonte
- Parte preclinica: nessuna
- Il preclinico valida il clinico? non applicabile: non esiste una parte preclinica
- Farmaci di laboratorio somministrati ai pazienti? non applicabile: nessun farmaco e' stato testato in laboratorio
- Alterazioni: requisito o reperto? il riarrangiamento di ALK precede il trattamento; le mutazioni di resistenza sono reperti alla recidiva

## 4-6. Split proposto e unita'

L'audit proponeva **2** unita'. La lettura ne sostiene **1**.

| Unita' | Tipo | Statement candidati |
| --- | --- | --- |
| `PU-PMID-31358542-clinical-cohort` | clinical_observational_cohort | `ES-V2-evidence-100003`, `ES-V2-evidence-100004` |

## 7-9. Qualificatori, provenienza, locator

Ogni dimensione nota porta la sua provenienza; la completezza e' verificata dal
costruttore, che solleva se un valore noto resta senza locator.

- Campi `unknown`: `comparator`, `exclusion_criteria`, `inclusion_criteria`, `prior_therapies`, `regimen`, `resection_status`, `setting`, `stage`
- Campi `not_applicable`: —
- Dimensioni non separabili: `intervention`

## 10. Statement

| Statement | Supporto | Stato candidato | Unita' |
| --- | --- | --- | --- |
| `ES-V2-evidence-100003` | direct_clinical_support | **candidate_ambiguous** | `PU-PMID-31358542-clinical-cohort` |
| `ES-V2-evidence-100004` | direct_clinical_support | **candidate_partial** | `PU-PMID-31358542-clinical-cohort` |

## 11. Terminologia

Nessuno scarto terminologico rilevato.

## 12. Propagazione

- Regole eseguite: 14
- Violazioni: **0**
- Propagabile: **no** — nessuna proposta lo e' prima dell'approvazione

## 13-15. Limiti

Nessun limite di accesso.

Rischio residuo: il rischio residuo non e' clinico/preclinico ma di sottogruppo: otto sottopopolazioni sovrapposte, e i dati aggregati per i TKI di seconda generazione possono essere attribuiti al singolo farmaco per errore

## 16. Domande per l'autore

1. Lo split clinico/preclinico e' respinto. Si conferma che l'unita' resta singola, o le otto sottopopolazioni giustificano uno split di sottogruppo?
2. ES-V2-evidence-100003 attribuisce a brigatinib una frequenza riportata per l'insieme dei TKI di seconda generazione. Va declassato a candidate_invalid?
3. La fonte era un falso positivo del rilevatore: va segnalata come caso di riferimento per la correzione dei segnali?

## 17. Stato

```
review_status                      = source_checked_review_proposal
human_reviewed                     = false
first_review_complete              = false
is_evaluable                       = false
requires_author_approval           = true
requires_second_independent_review = true
```

Una seconda revisione indipendente resta necessaria: questa fase ha letto la
fonte, non l'ha giudicata.


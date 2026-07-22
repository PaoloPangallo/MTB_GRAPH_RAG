# Prima revisione — BA-22b14dbcbc62e29b

## Come questa revisione è stata prodotta

| | |
|---|---|
| `reviewer_id` | `paolo_pangallo` |
| `reviewer_role` | `thesis_author_non_clinical` |
| `review_method` | `human_approved_llm_assisted_source_review` |
| `independent_review` | **false** |
| `clinical_reviewer` | **false** |
| `review_status` | `first_review_complete` |
| `requires_second_independent_review` | **true** |
| `is_evaluable_for_final_metrics` | **false** |

La revisione è stata approvata esplicitamente dall'autore della tesi, ma
preparata con assistenza di un modello linguistico. Non è quindi una revisione
clinica e non è indipendente.

Vale come **prima** annotazione. Non può entrare in nessuna metrica finale di
linking o di accordo, e nessuna delle decisioni qui sotto è gold.

---

## 1. Fonte

**PMID 22277784** — *Mechanisms of acquired crizotinib resistance in
ALK-rearranged lung cancers.*

Full text verificato in **PMC3385512**, interrogato in memoria e non conservato
nel repository. Restano `document_sha256`, posizione e esito di ogni locator, così
che una verifica futura sullo stesso documento debba dare gli stessi risultati.

### Locator

**10 su 10 verificati.**

| Locator | Esito | Tipo di corrispondenza |
|---|---|---|
| abstract | verified | inline_reference |
| Methods/Results | verified | inline_reference |
| Table 1 | verified | **label** |
| Figure 1C-D | verified | inline_reference (`Fig. 1C`) |
| Figure 1E | verified | inline_reference |
| Supplementary Figure S2 | verified | inline_reference (`fig. S2`) |
| Supplementary Figure S3C | verified | inline_reference (`fig. S3C`) |
| «To directly determine whether these mutations confer resistance» | verified | **exact** |
| «We focused on three ALK inhibitors» | verified | **exact** |
| «ALK fusion proteins are known hsp90 clients» | verified | **interpolated** |

L'ultimo merita una nota. La ricerca esatta falliva, perché il documento scrive
«ALK fusion proteins are known hsp90 **(heat shock protein 90)** clients». La
citazione è corretta e l'inciso è dell'editore. Dichiararla non verificata sarebbe
stato un falso negativo che screditava una citazione buona — ma il tipo di
corrispondenza resta `interpolated` e non `exact`, così che la tolleranza usata
sia visibile a chi legge.

## 2. Decisione di split

```
review_decision:                split_required
cohort_resolution:              cohort_resolved_into_clinical_and_preclinical_units
original_profile_unit_status:   superseded_by_reviewed_split
is_propagatable:                false
```

`PU-PMID-22277784-cohort-1` è **conservata**, non eliminata: i link e le metriche
prodotti prima della revisione la citano, e cancellarla renderebbe illeggibile la
loro storia. Non propaga più nulla e punta alle quattro unità che la sostituiscono.

Il motivo dello split: la fonte descrive una coorte clinica e tre serie di
esperimenti su cellule Ba/F3. Un profilo unico permetterebbe di attribuire la
popolazione dei 18 pazienti a un esperimento in vitro, o il setting preclinico ai
pazienti.

## 3. Le quattro unità

| Unità | Tipo | Locator |
|---|---|---|
| `…-clinical-crizotinib-resistant` | `clinical_observational_cohort` | abstract, Methods/Results, Table 1 |
| `…-baf3-crizotinib-panel` | `preclinical_in_vitro` | Fig. 1C-D, «To directly determine…» |
| `…-baf3-next-generation-alk-inhibitors` | `preclinical_in_vitro_comparative_pharmacology` | «We focused on three…», Fig. 1E, fig. S2 |
| `…-baf3-17aag` | `preclinical_in_vitro` | «ALK fusion proteins…», Fig. 1E, fig. S3C |

## 4. Qualificatori

**31 campi confermati · 20 `not_applicable` · 5 `unknown`.**

La distinzione fra gli ultimi due porta informazione e va tenuta. `unknown` dice
che nessuno lo ha ancora cercato; `not_applicable` dice che la domanda non si
pone. Chiedere la linea di terapia di un esperimento su linee cellulari non ha
risposta, e registrarlo come `unknown` suggerirebbe che qualcuno debba ancora
cercarla.

Sulla coorte clinica restano `unknown`: stadio, linea di terapia, stato di
resezione, regime, criteri di esclusione. Nessuno di questi è stato dedotto.

### Mapping degli interventi

| Termine della fonte | Termine mappato | Stringa letterale presente |
|---|---|---|
| `CH5424802` | alectinib | **no** |
| `17-AAG` | tanespimycin | **no** |

Entrambi hanno `mapping_status: requires_source_or_terminology_verification`.

Il caso di CH5424802 è quello che conta: il grafo V2 contiene «alectinib
hydrochloride», che nella fonte del 2012 **non compare**. Registrare
l'equivalenza in silenzio farebbe apparire una risposta clinica ad alectinib dove
esiste un esperimento in vitro su un codice di sviluppo.

## 5. Provenance

`qualifier_provenance_completeness` = **1.000**.

Ogni campo confermato porta: origine `primary_source_text`, i locator verificati
con il loro tipo di corrispondenza, la data di accesso, `span_hash` uguale
all'hash del documento PMC, e `asserted_by` che nomina **il metodo** oltre alla
persona — `paolo_pangallo (human_approved_llm_assisted_source_review)`. Chi legge
un singolo campo, mesi dopo, vede da solo come è stato prodotto.

## 6. Le dieci decisioni

**8 `valid_link` · 2 `partial_link`.**

| Statement | Unità | Esito | Nota |
|---|---|---|---|
| `…-100005` | clinica + Ba/F3 crizotinib | valid | G1202R, evidenza clinica e validazione funzionale |
| `…-1347` | Ba/F3 next-gen | **partial** | CH5424802: sensibilità ridotta, **non** risposta clinica ad alectinib |
| `…-1348` | Ba/F3 next-gen | **partial** | NVP-TAE684 conserva attività, potenza ridotta |
| `…-1352` | Ba/F3 17-AAG | valid | sensibilità in modello cellulare, solo preclinica |
| `…-1357` | clinica + Ba/F3 crizotinib | valid | adenocarcinoma ALK-positive, G1202R |
| `…-440` | clinica | valid | amplificazione del gene di fusione ALK |
| `…-441` | clinica + Ba/F3 crizotinib | valid | L1196M |
| `…-442` | clinica + Ba/F3 crizotinib | valid | S1206Y |
| `…-443` | clinica + Ba/F3 crizotinib | valid | 1151Tins |
| `…-444` | clinica + Ba/F3 crizotinib | valid | mutazione secondaria di ALK |

### Resistenza relativa, non completa

Sui due `partial_link` il qualificatore è `relative_reduced_sensitivity`, mai
`complete_resistance`. La distinzione non è terminologica: un farmaco che
conserva attività a concentrazione più alta e un farmaco inattivo portano a
decisioni cliniche diverse, e collassarli farebbe scartare il primo.

### Regole di propagazione, verificate

Le regole non sono documentate ma **controllate**: `check_propagation` fa fallire
la costruzione degli artefatti se sono violate, ed è provato su unità
deliberatamente scorrette.

- La popolazione dei 18 pazienti non compare su nessuna unità preclinica.
- Il setting preclinico non compare sulla coorte clinica.
- Nessuna unità Ba/F3 porta linea di terapia, terapie precedenti, stadio o stato
  di resezione.
- Ogni statement legato solo a unità precliniche dichiara
  `clinical_response_observed: false`.

## 7. Limiti

1. **La revisione non è indipendente e non è clinica.** È il limite che governa
   tutti gli altri.
2. **Nessuna metrica finale è calcolabile.** Precision, recall, F1, accordo e
   accuratezza restano `not_calculated`: un solo giudizio misurato contro se
   stesso non è una misura.
3. Il mapping CH5424802 → alectinib **non è verificato** su una terminologia
   controllata.
4. Cinque campi della coorte clinica restano `unknown`. Il full text potrebbe
   contenerli; questa revisione non li ha estratti e non li ha dedotti.
5. Le decisioni statement-level sono attribuite a livello di unità, non di
   singolo esperimento: per gli statement 441-444 la mutazione è registrata, ma
   il legame fra ciascuna mutazione e la specifica figura non è tracciato.

## 8. Necessità di seconda revisione

**Richiesta, e preferibilmente clinica.**

Il packet cieco è già pronto: `BB-659c05774521ee2e`. È stato verificato che non
contiene il nome del primo revisore, le quattro unità proposte, i rationale né gli
esiti `valid`/`partial` — questi ultimi vi compaiono solo dentro `allowed_values`,
cioè l'elenco delle risposte ammesse, che il secondo revisore deve conoscere.

Il gold resta `provisional_first_review` con `is_evaluable: false` su tutti e
dieci i record. La decisione di prima revisione vive in
`first_review_annotation.link_status`, deliberatamente **fuori** da
`final_status`: una prima revisione non indipendente non può essere il
riferimento contro cui si misura il linker.

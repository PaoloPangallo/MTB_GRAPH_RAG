# Modello dei claim adjudicato

Tre tipi tipizzati, piu' due stati di associazione che non sono claim.

## `atomic_intervention_claim`

Una proposizione con biomarcatore, disease scope, intervento, direzione, polarita',
source unit, locator e parent. E' l'unico tipo che afferma qualcosa di un singolo
intervento.

## `aggregate_intervention_claim`

Risultato riferito a un insieme di farmaci, a una classe o a un pannello non separabile.
`permits_member_specific_claims` resta `false`: un aggregato non autorizza mai la
derivazione di un claim per singolo membro. I membri sono i termini letterali della fonte.

## `regimen_claim`

Componenti canonicalizzati in ordine lessicografico; il risultato appartiene alla
combinazione e non si propaga. Un componente puo' avere un claim atomico proprio solo se
questo poggia su una `source_unit_id` diversa da quella del regime.

## `unsupported_association` e `unresolved_association`

Non sono claim. La prima e' una conclusione — la fonte non sostiene l'associazione — la
seconda una sospensione: abstract insufficiente, locator insufficiente, mapping pending o
scope incerto. Restano sul parent, auditabili, fuori dal retrieval primario. Tenerle
distinte conta: chiudere un'incertezza in un rifiuto perde l'informazione che serve a
riaprirla.

## Identita' dei claim

- formula: `sha256(graph_evidence_id + claim_type + canonical_intervention_or_regimen + biomarker + direction + polarity + source_unit_id)`
- claim: 15, identita' distinte: 15
- collisioni: 0
- indipendente dall'ordine: true
- stabile alla ricomputazione: true

I codici di sviluppo non vengono sostituiti dal nome generico nella canonicalizzazione.
Se lo fossero, l'ID renderebbe stabile un'equivalenza che nessuno ha verificato, e
verificarla dopo cambierebbe l'identita' di un claim gia' emesso.

## Claim approvati

| claim | tipo | parent | intervento o regime | biomarcatore | direzione |
| --- | --- | --- | --- | --- | --- |
| `CLM-091cf6602db85e2a2d41` | `atomic` | `evidence:296` | ponatinib | FGFR2::TACC3 Fusion | sensitivity |
| `CLM-0e59264facd7b2df0e67` | `atomic` | `evidence:1484` | alectinib hydrochloride | EML4::ALK Fusion AND ALK I1171S | resistance |
| `CLM-1fc4af943701d57d45ad` | `atomic` | `evidence:229` | gefitinib | EGFR L858R | sensitivity |
| `CLM-4a89bb28592af7ebaccf` | `regimen_claim` | `evidence:12131` | amivantamab + lazertinib | EGFR L858R OR EGFR Exon 19 Deletion | sensitivity |
| `CLM-4ffe85304f3ef5533b58` | `aggregate` | `evidence:275` | egfr tyrosine kinase inhibitor | EGFR L858R | sensitivity |
| `CLM-5ce49705979f72f174e9` | `regimen_claim` | `evidence:12156` | amivantamab + carboplatin + pemetrexed | EGFR L858R OR EGFR Exon 19 Deletion | sensitivity |
| `CLM-5ce532268b4aa1661311` | `atomic` | `evidence:841` | crizotinib | EML4::ALK Fusion AND ALK C1156Y | resistance |
| `CLM-68b84650d65add6c5696` | `atomic` | `evidence:296` | pazopanib hydrochloride | FGFR2::TACC3 Fusion | sensitivity |
| `CLM-89ea67ee7946d9ccd552` | `atomic` | `evidence:229` | erlotinib | EGFR L858R | sensitivity |
| `CLM-99ae092a3018b5b91808` | `atomic` | `evidence:841` | ceritinib | EML4::ALK Fusion AND ALK C1156Y | resistance |
| `CLM-9ab06b6945feea941252` | `atomic` | `evidence:11240` | erlotinib | EGFR L858R OR EGFR Exon 19 Deletion | sensitivity |
| `CLM-a7c903cf8d423f015e29` | `aggregate` | `evidence:1851` | bgj398 + pd173074 | FGFR2::BICC1 Fusion | sensitivity |
| `CLM-aae818bbc8ec735a255d` | `aggregate` | `evidence:1853` | bgj398 + pd173074 | FGFR2::AHCYL1 Fusion | sensitivity |
| `CLM-ac64c0e56246f6ea29ca` | `regimen_claim` | `evidence:11240` | erlotinib + ramucirumab | EGFR L858R OR EGFR Exon 19 Deletion | sensitivity |
| `CLM-bd4e24be0a4719119976` | `atomic` | `evidence:1483` | alectinib hydrochloride | ALK I1171N AND HIP1::ALK Fusion | resistance |

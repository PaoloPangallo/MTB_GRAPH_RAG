# Raccomandazione di integrazione

## Decisione

**B. SOLO VISUALIZZAZIONE**

Il grafo contiene abbastanza struttura per mostrare, in una superficie
separata, device, gene, piattaforma, campione e farmaco associato. Non contiene
abbastanza provenance e semantica clinica per materializzare claim companion
diagnostic in sicurezza.

Non implementare questa raccomandazione nel runtime in questa fase.

## Gate concettuali futuri

Questi gate sono proposte di dominio, non implementazioni:

| gate | input | pass | warning | audit/rejected | reason code esempio |
|---|---|---|---|---|---|
| diagnostic status | record/source | categoria esplicita e fonte | label CDx senza fonte | categoria contraddetta | DIAGNOSTIC_STATUS_UNVERIFIED |
| biomarker | gene/variant e assay | normalizzazione verificata | gene-level soltanto | mismatch | BIOMARKER_MISMATCH |
| disease | disease e scope | legame esplicito | scope non verificato | incompatibile | DISEASE_SCOPE_UNVERIFIED |
| assay | device/method | assay identificato | method incompleto | assente | ASSAY_UNSPECIFIED |
| associated therapy | intervention e relazione | relation documentata | sola associazione del grafo | relation contraddetta | THERAPY_ASSOCIATION_ONLY |
| diagnostic category | category | categoria supportata | categoria mancante | classificazione non supportata | CDX_CATEGORY_UNVERIFIED |
| regulatory context | status/jurisdiction | status con fonte | status missing | claim regolatoria non supportata | REGULATORY_STATUS_UNAVAILABLE |
| specimen | specimen type | requisito documentato | specimen solo riportato | mismatch | SPECIMEN_REPORTED_NOT_REQUIRED |
| provenance | source/unit/locator | passage claim-linked | parent-only | source missing | SOURCE_PARENT_ONLY |

Le semantiche pass, warning, audit e rejected devono restare separate dalle
classificazioni terapeutiche. Non riusare automaticamente primary, warning,
audit o rejected del dominio terapeutico.

## Dossier

La sezione proposta è “Verifica diagnostica e companion diagnostic” e dovrebbe
mostrare test disponibile, biomarcatore rilevato, malattia, terapia associata,
tecnologia, tipo di campione, fonte, stato della provenance, compatibilità e
limiti. Deve mostrare esplicitamente che un test associato non dimostra
l'efficacia della terapia.

## Relazione con ontology shadow e PMID

Ontology shadow può aiutare solo nella normalizzazione locale verificata di
test, biomarcatore, malattia e intervento. Non deve convertire gerarchie in
equivalenze. Il PMID può collegare una pubblicazione candidata; il supporto
claim-specifico richiede un passaggio testuale e un locator reale.

## Fasi necessarie prima di qualsiasi integrazione

1. aggiungere un record diagnostico con source unit e locator;
2. definire categorie e relazioni con semantica esplicita;
3. separare associazione, selezione e requisito terapeutico;
4. validare disease, biomarker, assay e provenance;
5. eseguire un pilota indipendente senza modificare output V3;
6. solo dopo valutare una superficie di visualizzazione o un gate secondario.

# Modello concettuale diagnostico

## Categorie proposte

| categoria | significato progettuale | supportata oggi dal grafo? |
|---|---|---|
| DIAGNOSTIC_EVIDENCE | evidenza su diagnosi, classificazione o biomarcatore | parzialmente, tramite Evidence e le due claim attive |
| COMPANION_DIAGNOSTIC | test collegato all'uso sicuro/appropriato di una terapia specifica | nodo/relazione nominati, ma semantica claim-safe non completa |
| COMPLEMENTARY_DIAGNOSTIC | test informativo per una terapia senza requisito dimostrato | non supportata come categoria esplicita |
| ASSAY_DETECTION | assay capace di rilevare un biomarcatore | parzialmente: gene, piattaforma e campione possono essere presenti |

La label CompanionDiagnostic è un fatto dello schema. Non è sufficiente da
sola a ricostruire approvazione regolatoria, requisito terapeutico o
applicabilità clinica.

## Entità

Il modello futuro dovrebbe separare DiagnosticRecord, Biomarker, Disease,
Intervention, Assay, Publication e EvidencePassage. CompanionDiagnostic non
dovrebbe essere usato come sinonimo di ogni diagnostica associata a un farmaco.

## Provenance

Ogni eventuale claim futura dovrebbe conservare identificatore documentale,
livello della fonte, source unit e locator. Un PMID parent-level identifica una
pubblicazione candidata; non dimostra il supporto claim-specifico.

## Ontology shadow

Il modulo ontology shadow può in futuro normalizzare sinonimi del device,
identificatori del biomarcatore, gerarchie di malattia, e principio attivo
versus sale/formulazione. Le gerarchie restano informative: RELATED non è
equivalenza e una relazione parent/child non dimostra applicabilità clinica.
Non esiste ancora un collegamento runtime tra i due moduli.

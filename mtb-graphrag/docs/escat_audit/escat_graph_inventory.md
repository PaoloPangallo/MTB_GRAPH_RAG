# ESCAT nel Knowledge Graph e negli asset locali

## Posizione effettiva

Lo snapshot contiene le label ClinicalTrial, CompanionDiagnostic, Disease,
Drug, Evidence, Gene, MolecularProfile, Publication, Variant. Non contiene un
nodo ESCAT o un nodo di tier.

Proprietà di Evidence:

- citation_id
- disease
- doid
- evidence_direction
- evidence_id
- evidence_level
- evidence_statement
- evidence_type
- rating
- significance
- source_type
- variant_origin

Non è presente una proprietà escat, escat_level, escat_tier,
actionability_level, evidence_tier o clinical_actionability. Non è presente
un arco con semantica ESCAT.

Altri campi potenzialmente confondibili non sono ESCAT:

- Gene.categories contiene anche la stringa CLINICALLY ACTIONABLE in alcuni
  record di audit; è una categoria del gene, non una classificazione ESCAT.
- MolecularProfile.evidence_score è un campo di profilo, non un tier ESCAT.
- Evidence.evidence_level contiene scale diverse e non porta il sistema
  tassonomico nel record V2.
- Drug.approved è uno stato del farmaco, non l'actionability ESCAT della
  coppia biomarcatore-malattia-terapia.

## Strutture che ammettono ESCAT ma non lo popolano

Il JSON Schema EvidenceStatement definisce evidence_level come oggetto con:

- system, che può assumere anche escat;
- original_value;
- normalized_tier;
- interpretation;
- provenance.

Lo stesso schema specifica che il valore originale deve essere conservato e
che scale diverse non devono essere convertite silenziosamente. Nei record
attivi ispezionati non esiste però alcun oggetto evidence_level nel repository
qualified claim e non esiste alcun record con system=escat.

## Valori generici osservati

Nei 1.525 record raw degli audit locali sono stati osservati valori del campo
Evidence.evidence_level: A, B, C, D, LEVEL_2, LEVEL_3A e LEVEL_R2. Sono
riportati come valori originali del campo, non come ESCAT. Il conteggio è
limitato ai raw record locali e non è una distribuzione completa di tutti i
4.860 nodi Evidence dello snapshot.

## Provenance ESCAT

Non esiste un record ESCAT da cui leggere biomarcatore, alterazione, malattia,
terapia, direzione, fonte, PMID/DOI, versione, timestamp o curator/provider.
Il timestamp dello snapshot identifica l'audit del grafo, non una versione
ESCAT.

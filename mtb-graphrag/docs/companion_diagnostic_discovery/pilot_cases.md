# Casi pilota locali

I casi sono scelti da audit e snapshot già presenti. Nessun dato è stato
arricchito con fonti live.

## Caso 1 — FGFR2 fusion in intrahepatic cholangiocarcinoma

Caso strutturato: FGFR2::BICC1 Fusion e FGFR2::AHCYL1 Fusion, malattia
Intrahepatic Cholangiocarcinoma, assay whole transcriptome sequencing con
RT-PCR screening.

Record recuperabili: evidence:1846 e evidence:1847 diventano le due claim
diagnostiche attive; il grafo CDx non espone un device specifico per questi
record.

Relazione biomarcatore: il biomarcatore è nel record Evidence/claim; il
collegamento a un nodo CompanionDiagnostic corrispondente non è dimostrato.
Relazione terapia: assente nelle claim e nel parent; non viene inferita dalla
presenza di altri nodi Drug. Fonte: PMID:24122810, source unit
PU-PMID-24122810-cohort-1, abstract locator. Campi mancanti: device,
categoria, terapia, stato regolatorio, giurisdizione, provenance CDx.

Sezione dossier possibile: “Verifica diagnostica e companion diagnostic” con
diagnostic evidence, biomarcatore, metodo, fonte e limiti; non una attestazione
di companion diagnostic.

## Caso 2 — IDH1, Abbott RealTime IDH1

Caso strutturato nello sample del catalogo: device Abbott RealTime IDH1,
gene_symbol IDH1, platform_type PCR, specimen_types Bone marrow e Peripheral
Blood, associated_drug Ivosidenib oppure Olutasidenib.

Record recuperabili: un nodo CompanionDiagnostic e un arco
Drug-HAS_COMPANION_DIAGNOSTIC per ciascuna associazione registrata nello
snapshot. Non esiste nel campione di schema una source unit o un passage
claim-specifico.

Relazione biomarcatore: gene-level, presente come gene_symbol/DIAGNOSES_GENE.
Relazione terapia: associazione strutturale al Drug, non terapia “required”.
Relazione malattia: non disponibile come legame CDx-specifico. Fonte:
non disponibile sul nodo campione. Campi mancanti: PMID/locator, disease,
categoria diagnostica, regolatorio, giurisdizione, performance e relazione di
selezione.

Sezione dossier possibile: visualizzazione di test, gene, piattaforma,
campione e farmaco associato, con badge “associazione del grafo; supporto
claim-specifico non verificato”.

## Caso 3 — EGFR L858R audit context

Caso locale PILOT-C1-EGFR-L858R-CONTEXT: EGFR L858R con categorie di malattia,
farmaci, contesto e citation IDs nell'audit snapshot.

Record diagnostici recuperabili: nessun nodo CompanionDiagnostic viene
materializzato nel record di audit mostrato. Il percorso locale contiene
Evidence e relazioni farmacologiche, ma non una relazione test-specifica.

Relazione biomarcatore: presente nel contesto molecolare. Relazione terapia:
presente nei record terapeutici, ma non come relazione test--terapia.
Relazione malattia: presente nei record di contesto, non CDx-specifica. Fonte:
citation IDs locali secondo l'audit; non viene promossa a supporto CDx.
Campi mancanti: assay/device, categoria, specimen, technology e passage
diagnostico.

## Caso 4 — ALK G1202R audit context

Caso locale PILOT-A2-ALK-G1202R: ALK G1202R con record di resistenza,
sensibilità, mutazioni composte e trial.

Record diagnostici recuperabili: nessun record CDx claim-linked nel caso
locale. Il biomarcatore e gli interventi sono presenti in altre strutture di
evidence, ma non esiste un collegamento test-specifico verificabile.

Relazione biomarcatore e terapia: disponibili separatamente nel contesto
terapeutico; relazione test--terapia, fonte CDx e locator sono mancanti.

## Caso 5 — RMI2

PILOT-N1-RMI2-SNAPSHOT registra gene_present=true, molecular_profile_count=0,
evidence_count=0, interact_with_drug_count=0 e trial_count=0. Non è presente
un record diagnostico. Il caso mostra che la presenza di un gene non implica
la presenza di assay, companion diagnostic o terapia associata.

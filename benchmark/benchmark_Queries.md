// ============================================================================
// QUERY DI VALIDAZIONE BENCHMARK — 10 CASI MTB
// Scopo: verificare che il grafo Neo4j restituisca la raccomandazione corretta
// per ciascun caso benchmark prima di implementare gli agenti.
// 
// Come usarle: esegui ogni query nel browser Neo4j (GraphRAGTesi).
// Il risultato atteso è indicato nel commento sopra ogni query.
// Se il farmaco atteso NON appare nei risultati, il caso non è coperto
// dal grafo con evidenza sufficiente — va documentato come gap.
// ============================================================================


// ----------------------------------------------------------------------------
// BENCH-001 — NSCLC + EGFR L858R → Osimertinib (ESCAT I-A)
// Risultato atteso: Osimertinib, Afatinib, Dacomitinib, Erlotinib, Gefitinib
// Almeno uno con evidence_level = "A" e significance CONTAINS "Sensitivity"
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "EGFR"})
-[:HAS_VARIANT]->(v:Variant {variant_name: "L858R"})
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND e.disease CONTAINS "Non-small Cell"
RETURN 
  "BENCH-001" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-002 — NSCLC + ALK Fusion → Alectinib (ESCAT I-A)
// Risultato atteso: Alectinib, Crizotinib, Brigatinib, Lorlatinib
// Cerca varianti che contengono "Fusion" nel nome
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "ALK"})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND (v.variant_name CONTAINS "Fusion" OR v.variant_name CONTAINS "fusion"
       OR mp.name CONTAINS "Fusion" OR mp.name CONTAINS "fusion")
RETURN 
  "BENCH-002" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  mp.name AS molecular_profile,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-003 — Melanoma + BRAF V600E → Dabrafenib+Trametinib (ESCAT I-A)
// Risultato atteso: Vemurafenib, Dabrafenib, Trametinib con disease Melanoma
// Test critico: verificare che la disease sia "Melanoma" e NON "Colorectal"
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "BRAF"})
-[:HAS_VARIANT]->(v:Variant {variant_name: "V600E"})
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND (e.disease CONTAINS "Melanoma" OR e.disease CONTAINS "melanoma")
RETURN 
  "BENCH-003" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-004 — Breast Cancer HER2+ + ERBB2 Amplification → Trastuzumab (ESCAT I-A)
// Risultato atteso: Trastuzumab, Pertuzumab, T-DM1, Lapatinib con Breast Cancer
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "ERBB2"})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND (v.variant_name CONTAINS "Amplification" OR mp.name CONTAINS "Amplification")
  AND (e.disease CONTAINS "Breast" OR e.disease CONTAINS "breast")
RETURN 
  "BENCH-004" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  mp.name AS molecular_profile,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-005 — Ovarian Cancer + BRCA1 Mutation → Olaparib (ESCAT I-A)
// Risultato atteso: Olaparib, Niraparib, Rucaparib con Ovarian Cancer
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "BRCA1"})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND (e.disease CONTAINS "Ovarian" OR e.disease CONTAINS "ovarian"
       OR e.disease CONTAINS "Breast" OR e.disease CONTAINS "breast")
RETURN 
  "BENCH-005" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-006 — CML + BCR-ABL1 Fusion → Imatinib (ESCAT I-A)
// Risultato atteso: Imatinib, Dasatinib, Nilotinib con CML
// Nota: in CIViC ABL1 ha la fusione BCR::ABL1 come profilo molecolare
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "ABL1"})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND (e.disease CONTAINS "Leukemia" OR e.disease CONTAINS "leukemia"
       OR e.disease CONTAINS "CML")
RETURN 
  "BENCH-006" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  mp.name AS molecular_profile,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-007 — mCRC + BRAF V600E → Encorafenib+Cetuximab (ESCAT I-A)
// Risultato atteso: farmaci con disease Colorectal Cancer
// TEST CRITICO: stessa variante BENCH-003 ma tumore diverso → farmaco diverso
// Il sistema deve distinguere melanoma vs CRC per la stessa mutazione BRAF V600E
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "BRAF"})
-[:HAS_VARIANT]->(v:Variant {variant_name: "V600E"})
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND (e.disease CONTAINS "Colorectal" OR e.disease CONTAINS "colorectal"
       OR e.disease CONTAINS "Colon" OR e.disease CONTAINS "colon")
RETURN 
  "BENCH-007" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  e.evidence_level AS evidence_level,
  e.significance AS significance,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 15;


// ----------------------------------------------------------------------------
// BENCH-008 — Breast Cancer HR+ + PIK3CA Mutation → Alpelisib+Fulvestrant (ESCAT I-A)
// Risultato atteso: Alpelisib (o Idelalisib, BKM120) con Breast Cancer
// Nota: PIK3CA ha 76 evidenze Gold nel grafo — caso molto ricco
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "PIK3CA"})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND e.evidence_level IN ["A", "B"]
  AND (e.disease CONTAINS "Breast" OR e.disease CONTAINS "breast")
RETURN 
  "BENCH-008" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-009 — GIST + KIT Exon 11 Mutation → Imatinib (ESCAT I-A)
// Risultato atteso: Imatinib con GIST o Gastrointestinal Stromal Tumor
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "KIT"})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND (e.disease CONTAINS "Gastrointestinal Stromal" 
       OR e.disease CONTAINS "GIST"
       OR v.variant_name CONTAINS "Exon 11")
RETURN 
  "BENCH-009" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ----------------------------------------------------------------------------
// BENCH-010 — AML + FLT3 ITD → Midostaurin (ESCAT I-A)
// Risultato atteso: Midostaurin, Gilteritinib con AML / Leukemia
// ----------------------------------------------------------------------------
MATCH (g:Gene {hugo_symbol: "FLT3"})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND (v.variant_name CONTAINS "ITD" 
       OR v.variant_name CONTAINS "Internal Tandem"
       OR mp.name CONTAINS "ITD")
  AND (e.disease CONTAINS "Leukemia" OR e.disease CONTAINS "AML")
RETURN 
  "BENCH-010" AS case_id,
  g.hugo_symbol AS gene,
  v.variant_name AS variant,
  mp.name AS molecular_profile,
  e.evidence_level AS evidence_level,
  d.drug_name AS recommended_drug,
  e.disease AS tumor_type,
  e.citation_id AS pmid
ORDER BY e.evidence_level ASC
LIMIT 10;


// ============================================================================
// QUERY RIASSUNTIVA — Esegui questa per vedere tutti i 10 casi insieme
// Mostra quante evidenze trova il grafo per ciascun caso benchmark
// ============================================================================
UNWIND [
  {case_id: "BENCH-001", gene: "EGFR", variant: "L858R", disease: "Non-small Cell"},
  {case_id: "BENCH-002", gene: "ALK", variant: "Fusion", disease: "Non-small Cell"},
  {case_id: "BENCH-003", gene: "BRAF", variant: "V600E", disease: "Melanoma"},
  {case_id: "BENCH-004", gene: "ERBB2", variant: "Amplification", disease: "Breast"},
  {case_id: "BENCH-005", gene: "BRCA1", variant: "Mutation", disease: "Ovarian"},
  {case_id: "BENCH-006", gene: "ABL1", variant: "BCR-ABL", disease: "Leukemia"},
  {case_id: "BENCH-007", gene: "BRAF", variant: "V600E", disease: "Colorectal"},
  {case_id: "BENCH-008", gene: "PIK3CA", variant: "Mutation", disease: "Breast"},
  {case_id: "BENCH-009", gene: "KIT", variant: "Exon 11", disease: "Gastrointestinal Stromal"},
  {case_id: "BENCH-010", gene: "FLT3", variant: "ITD", disease: "Leukemia"}
] AS bench
MATCH (g:Gene {hugo_symbol: bench.gene})
-[:HAS_VARIANT]->(v:Variant)
-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_type = "Predictive"
  AND e.significance CONTAINS "Sensitivity"
  AND e.disease CONTAINS bench.disease
RETURN 
  bench.case_id AS case_id,
  bench.gene AS gene,
  bench.variant AS variant_cercata,
  count(DISTINCT d) AS farmaci_trovati,
  count(DISTINCT e) AS evidenze_trovate,
  collect(DISTINCT e.evidence_level)[0..3] AS livelli_evidenza,
  collect(DISTINCT d.drug_name)[0..3] AS top_farmaci
ORDER BY case_id;

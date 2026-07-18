// ============================================================================
// NEO4J IMPORT CYPHER - KNOWLEDGE GRAPH ONCOLOGICO (MTB / GraphRAG)
// ============================================================================
//
// NOTA OPERATIVA:
// 1. Copiare tutti i file CSV generati nella cartella "Clean_Graph_Data" 
//    all'interno della directory "import" dell'istanza Neo4j in uso.
// 2. Eseguire le query sotto indicate in ordine (Constraints prima di tutto).
// ============================================================================

// ----------------------------------------------------------------------------
// STEP 1: UNIQUE CONSTRAINTS & INDICES (Eseguire per primi!)
// ----------------------------------------------------------------------------

CREATE CONSTRAINT gene_entrez_id IF NOT EXISTS FOR (g:Gene) REQUIRE g.entrez_id IS UNIQUE;
CREATE CONSTRAINT variant_id IF NOT EXISTS FOR (v:Variant) REQUIRE v.variant_id IS UNIQUE;
CREATE CONSTRAINT molecular_profile_id IF NOT EXISTS FOR (m:MolecularProfile) REQUIRE m.molecular_profile_id IS UNIQUE;
CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (e:Evidence) REQUIRE e.evidence_id IS UNIQUE;
CREATE CONSTRAINT drug_concept_id IF NOT EXISTS FOR (d:Drug) REQUIRE d.concept_id IS UNIQUE;
CREATE CONSTRAINT companion_device_id IF NOT EXISTS FOR (c:CompanionDiagnostic) REQUIRE c.device_id IS UNIQUE;

CREATE INDEX gene_hugo IF NOT EXISTS FOR (g:Gene) ON (g.hugo_symbol);
CREATE INDEX drug_name IF NOT EXISTS FOR (d:Drug) ON (d.drug_name);

// ----------------------------------------------------------------------------
// STEP 2: INGESTION NODI (NODES)
// ----------------------------------------------------------------------------

// 2.1 Ingestion Nodi Gene
LOAD CSV WITH HEADERS FROM "file:///node_gene.csv" AS row
MERGE (g:Gene {entrez_id: toInteger(row.entrez_id)})
ON CREATE SET 
  g.hugo_symbol = row.hugo_symbol,
  g.gene_type = row.gene_type,
  g.is_oncokb_annotated = toBoolean(row.is_oncokb_annotated),
  g.grch38_isoform = row.grch38_isoform,
  g.grch38_refseq = row.grch38_refseq,
  g.aliases = CASE WHEN row.aliases IS NOT NULL AND row.aliases <> "" THEN split(row.aliases, ";") ELSE [] END,
  g.categories = CASE WHEN row.categories IS NOT NULL AND row.categories <> "" THEN split(row.categories, ";") ELSE [] END,
  g.civic_description = row.civic_description;

// 2.2 Ingestion Nodi Drug
LOAD CSV WITH HEADERS FROM "file:///node_drug.csv" AS row
MERGE (d:Drug {concept_id: row.concept_id})
ON CREATE SET 
  d.drug_claim_name = row.drug_claim_name,
  d.nomenclature = row.nomenclature,
  d.drug_name = row.drug_name,
  d.approved = toBoolean(row.approved),
  d.immunotherapy = toBoolean(row.immunotherapy),
  d.anti_neoplastic = toBoolean(row.anti_neoplastic),
  d.source_db_name = row.source_db_name,
  d.source_db_version = row.source_db_version,
  d.fda_approval_year = toInteger(row.fda_approval_year),
  d.biomarker = row.biomarker,
  d.drug_class = row.drug_class,
  d.mechanism = row.mechanism;

// 2.3 Ingestion Nodi Variant
LOAD CSV WITH HEADERS FROM "file:///node_variant.csv" AS row
MERGE (v:Variant {variant_id: toInteger(row.variant_id)})
ON CREATE SET 
  v.variant_name = row.variant_name,
  v.feature_type = row.feature_type,
  v.hgvs_descriptions = CASE WHEN row.hgvs_descriptions IS NOT NULL AND row.hgvs_descriptions <> "" THEN split(row.hgvs_descriptions, ";") ELSE [] END,
  v.chromosome = row.chromosome,
  v.start = toInteger(row.start),
  v.stop = toInteger(row.stop),
  v.reference_bases = row.reference_bases,
  v.variant_bases = row.variant_bases,
  v.variant_types = row.variant_types,
  v.allele_registry_id = row.allele_registry_id,
  v.civic_url = row.civic_url;

// 2.4 Ingestion Nodi Molecular Profile
LOAD CSV WITH HEADERS FROM "file:///node_molecular_profile.csv" AS row
MERGE (m:MolecularProfile {molecular_profile_id: toInteger(row.molecular_profile_id)})
ON CREATE SET 
  m.name = row.name,
  m.summary = row.summary,
  m.evidence_score = toFloat(row.evidence_score),
  m.aliases = CASE WHEN row.aliases IS NOT NULL AND row.aliases <> "" THEN split(row.aliases, ";") ELSE [] END;

// 2.5 Ingestion Nodi Evidence
LOAD CSV WITH HEADERS FROM "file:///node_evidence.csv" AS row
MERGE (e:Evidence {evidence_id: toInteger(row.evidence_id)})
ON CREATE SET 
  e.evidence_type = row.evidence_type,
  e.evidence_level = row.evidence_level,
  e.evidence_direction = row.evidence_direction,
  e.significance = row.significance,
  e.evidence_statement = row.evidence_statement,
  e.citation_id = CASE WHEN row.citation_id IS NOT NULL AND row.citation_id <> "" THEN split(row.citation_id, ";") ELSE [] END,
  e.source_type = row.source_type,
  e.rating = toInteger(row.rating),
  e.variant_origin = row.variant_origin,
  e.disease = row.disease,
  e.doid = row.doid;

// 2.6 Ingestion Nodi Companion Diagnostic
LOAD CSV WITH HEADERS FROM "file:///node_companion_diagnostic.csv" AS row
MERGE (c:CompanionDiagnostic {device_id: row.device_id})
ON CREATE SET 
  c.device_name = row.device_name,
  c.platform_type = row.platform_type,
  c.specimen_types = CASE WHEN row.specimen_types IS NOT NULL AND row.specimen_types <> "" THEN split(row.specimen_types, ";") ELSE [] END,
  c.gene_symbol = row.gene,
  c.associated_drug = row.drug;


// ----------------------------------------------------------------------------
// STEP 3: INGESTION ARCHI (RELATIONSHIPS)
// ----------------------------------------------------------------------------

// 3.1 Arco: (:Gene)-[:HAS_VARIANT]->(:Variant)
LOAD CSV WITH HEADERS FROM "file:///edge_has_variant.csv" AS row
MATCH (g:Gene {entrez_id: toInteger(row.source_entrez_id)})
MATCH (v:Variant {variant_id: toInteger(row.target_variant_id)})
MERGE (g)-[:HAS_VARIANT]->(v);

// 3.2 Arco: (:Variant)-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
LOAD CSV WITH HEADERS FROM "file:///edge_in_molecular_profile.csv" AS row
MATCH (v:Variant {variant_id: toInteger(row.source_variant_id)})
MATCH (m:MolecularProfile {molecular_profile_id: toInteger(row.target_molecular_profile_id)})
MERGE (v)-[:IN_MOLECULAR_PROFILE]->(m);

// 3.3 Arco: (:MolecularProfile)-[:HAS_EVIDENCE]->(:Evidence)
LOAD CSV WITH HEADERS FROM "file:///edge_has_evidence.csv" AS row
MATCH (m:MolecularProfile {molecular_profile_id: toInteger(row.source_molecular_profile_id)})
MATCH (e:Evidence {evidence_id: toInteger(row.target_evidence_id)})
MERGE (m)-[:HAS_EVIDENCE]->(e);

// 3.4 Arco: (:Evidence)-[:TARGETS_DRUG]->(:Drug)
LOAD CSV WITH HEADERS FROM "file:///edge_targets_drug.csv" AS row
MATCH (e:Evidence {evidence_id: toInteger(row.source_evidence_id)})
MATCH (d:Drug {concept_id: row.target_drug_concept_id})
MERGE (e)-[r:TARGETS_DRUG]->(d)
ON CREATE SET 
  r.evidence_level = row.evidence_level,
  r.significance = row.significance,
  r.evidence_direction = row.evidence_direction;

// 3.5 Arco: (:Gene)-[:INTERACTS_WITH]->(:Drug)
LOAD CSV WITH HEADERS FROM "file:///edge_interacts_with.csv" AS row
MATCH (g:Gene {entrez_id: toInteger(row.source_gene_entrez_id)})
MATCH (d:Drug {concept_id: row.target_drug_concept_id})
MERGE (g)-[r:INTERACTS_WITH {interaction_type: row.interaction_type, source_db: row.source_db}]->(d)
ON CREATE SET 
  r.interaction_score = toFloat(row.interaction_score);

// 3.6 Arco: (:Drug)-[:HAS_COMPANION_DIAGNOSTIC]->(:CompanionDiagnostic)
LOAD CSV WITH HEADERS FROM "file:///edge_has_companion_diagnostic.csv" AS row
MATCH (d:Drug {concept_id: row.source_drug_concept_id})
MATCH (c:CompanionDiagnostic {device_id: row.target_device_id})
MERGE (d)-[:HAS_COMPANION_DIAGNOSTIC]->(c);

// 3.7 Arco: (:CompanionDiagnostic)-[:DIAGNOSES_GENE]->(:Gene)
LOAD CSV WITH HEADERS FROM "file:///edge_diagnoses_gene.csv" AS row
MATCH (c:CompanionDiagnostic {device_id: row.source_device_id})
MATCH (g:Gene {entrez_id: toInteger(row.target_gene_entrez_id)})
MERGE (c)-[:DIAGNOSES_GENE]->(g);


// ============================================================================
// CLINICALTRIALS.GOV ADDIZIONALE INGESTION
// ============================================================================

// 1. Constraints
CREATE CONSTRAINT clinical_trial_nct_id IF NOT EXISTS FOR (c:ClinicalTrial) REQUIRE c.nct_id IS UNIQUE;

// 2. Ingestion Nodi ClinicalTrial (senza criteri di eleggibilità)
LOAD CSV WITH HEADERS FROM "file:///nodes_clinical_trials.csv" AS row
MERGE (c:ClinicalTrial {nct_id: row.nct_id})
ON CREATE SET 
  c.title = row.title,
  c.status = row.status,
  c.phase = row.phase,
  c.conditions = CASE WHEN row.conditions IS NOT NULL AND row.conditions <> "" THEN split(row.conditions, " | ") ELSE [] END,
  c.keywords = CASE WHEN row.keywords IS NOT NULL AND row.keywords <> "" THEN split(row.keywords, " | ") ELSE [] END,
  c.interventions = CASE WHEN row.interventions IS NOT NULL AND row.interventions <> "" THEN split(row.interventions, " | ") ELSE [] END;

// 3. Archi: (:ClinicalTrial)-[:ASSOCIATED_GENE]->(:Gene)
LOAD CSV WITH HEADERS FROM "file:///edges_trial_gene.csv" AS row
MATCH (c:ClinicalTrial {nct_id: row.nct_id})
MATCH (g:Gene {hugo_symbol: row.gene_symbol})
MERGE (c)-[r:ASSOCIATED_GENE]->(g)
ON CREATE SET r.source = row.source;

// 4. Archi: (:ClinicalTrial)-[:TESTS_DRUG]->(:Drug)
LOAD CSV WITH HEADERS FROM "file:///edges_trial_drug.csv" AS row
MATCH (c:ClinicalTrial {nct_id: row.nct_id})
MATCH (d:Drug {drug_name: row.drug_name_normalized})
MERGE (c)-[r:TESTS_DRUG]->(d)
ON CREATE SET r.raw_name = row.drug_name_raw;


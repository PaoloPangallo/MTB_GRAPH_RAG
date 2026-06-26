
// ============================================================================
// CARICAMENTO NODI DISEASE E PUBLICATION IN NEO4J
// Script generato automaticamente da estrai_disease_publication_neo4j.py
// Data: 2026-05-31
// 
// PREREQUISITI:
//   1. Neo4j Desktop aperto con il database GraphRAGTesi attivo
//   2. I 4 file CSV nella cartella Neo4j import:
//      C:\Users\paolo\Neo4jDesktop2\Data\dbms\dbms-c1022817-b4f0-4d0d-a4ec-ee39e0dff0c9\import/civic_diseases.csv
//      C:\Users\paolo\Neo4jDesktop2\Data\dbms\dbms-c1022817-b4f0-4d0d-a4ec-ee39e0dff0c9\import/civic_publications.csv
//      C:\Users\paolo\Neo4jDesktop2\Data\dbms\dbms-c1022817-b4f0-4d0d-a4ec-ee39e0dff0c9\import/civic_evidence_disease_links.csv
//      C:\Users\paolo\Neo4jDesktop2\Data\dbms\dbms-c1022817-b4f0-4d0d-a4ec-ee39e0dff0c9\import/civic_evidence_publication_links.csv
//
// ESECUZIONE: copia e incolla nel Neo4j Browser (GraphRAGTesi)
// ============================================================================


// ----------------------------------------------------------------------------
// STEP 1 — CONSTRAINT E INDICI
// Esegui prima questo blocco e aspetta che finisca
// ----------------------------------------------------------------------------

CREATE CONSTRAINT disease_id_unique IF NOT EXISTS
FOR (d:Disease) REQUIRE d.disease_id IS UNIQUE;

CREATE CONSTRAINT disease_name_unique IF NOT EXISTS
FOR (d:Disease) REQUIRE d.name IS UNIQUE;

CREATE CONSTRAINT publication_pmid_unique IF NOT EXISTS
FOR (p:Publication) REQUIRE p.pmid IS UNIQUE;

CREATE INDEX disease_doid IF NOT EXISTS
FOR (d:Disease) ON (d.doid);

CREATE INDEX publication_source_type IF NOT EXISTS
FOR (p:Publication) ON (p.source_type);

// Verifica constraint creati
SHOW CONSTRAINTS;


// ----------------------------------------------------------------------------
// STEP 2 — CARICA NODI Disease (335 nodi attesi)
// ----------------------------------------------------------------------------

LOAD CSV WITH HEADERS FROM 'file:///civic_diseases.csv' AS row
MERGE (d:Disease {name: row.disease})
ON CREATE SET
  d.disease_id  = toInteger(row.disease_id),
  d.doid        = CASE WHEN row.doid <> '' THEN toInteger(row.doid) ELSE null END,
  d.doid_uri    = CASE WHEN row.doid_uri <> '' THEN row.doid_uri ELSE null END
ON MATCH SET
  d.disease_id  = toInteger(row.disease_id),
  d.doid        = CASE WHEN row.doid <> '' THEN toInteger(row.doid) ELSE null END,
  d.doid_uri    = CASE WHEN row.doid_uri <> '' THEN row.doid_uri ELSE null END
RETURN count(*) AS disease_caricate;


// ----------------------------------------------------------------------------
// STEP 3 — CARICA NODI Publication (2234 nodi attesi)
// ----------------------------------------------------------------------------

LOAD CSV WITH HEADERS FROM 'file:///civic_publications.csv' AS row
MERGE (p:Publication {pmid: toInteger(row.pmid)})
ON CREATE SET
  p.source_type      = row.source_type,
  p.citation_text    = row.citation_text,
  p.year             = CASE WHEN row.year <> '' THEN toInteger(row.year) ELSE null END,
  p.pubmed_url       = CASE WHEN row.pubmed_url <> '' THEN row.pubmed_url ELSE null END,
  p.asco_abstract_id = CASE WHEN row.asco_abstract_id <> '' THEN row.asco_abstract_id ELSE null END
ON MATCH SET
  p.source_type      = row.source_type,
  p.citation_text    = row.citation_text,
  p.year             = CASE WHEN row.year <> '' THEN toInteger(row.year) ELSE null END,
  p.pubmed_url       = CASE WHEN row.pubmed_url <> '' THEN row.pubmed_url ELSE null END,
  p.asco_abstract_id = CASE WHEN row.asco_abstract_id <> '' THEN row.asco_abstract_id ELSE null END
RETURN count(*) AS publication_caricate;


// ----------------------------------------------------------------------------
// STEP 4 — CREA ARCHI Evidence → Disease (HAS_DISEASE)
// 4855 archi attesi
// ----------------------------------------------------------------------------

LOAD CSV WITH HEADERS FROM 'file:///civic_evidence_disease_links.csv' AS row
MATCH (e:Evidence {evidence_id: toInteger(row.evidence_id)})
MATCH (d:Disease {disease_id: toInteger(row.disease_id)})
MERGE (e)-[:HAS_DISEASE]->(d)
RETURN count(*) AS archi_has_disease;


// ----------------------------------------------------------------------------
// STEP 5 — CREA ARCHI Evidence → Publication (CITED_IN)
// 4855 archi attesi (uno per evidenza)
// ----------------------------------------------------------------------------

LOAD CSV WITH HEADERS FROM 'file:///civic_evidence_publication_links.csv' AS row
MATCH (e:Evidence {evidence_id: toInteger(row.evidence_id)})
MATCH (p:Publication {pmid: toInteger(row.pmid)})
MERGE (e)-[:CITED_IN]->(p)
RETURN count(*) AS archi_cited_in;


// ----------------------------------------------------------------------------
// STEP 6 — VERIFICA FINALE
// ----------------------------------------------------------------------------

// Conta nodi caricati
MATCH (d:Disease) RETURN 'Disease' AS tipo, count(*) AS totale
UNION ALL
MATCH (p:Publication) RETURN 'Publication' AS tipo, count(*) AS totale
UNION ALL
MATCH ()-[r:HAS_DISEASE]->() RETURN 'HAS_DISEASE' AS tipo, count(*) AS totale
UNION ALL
MATCH ()-[r:CITED_IN]->() RETURN 'CITED_IN' AS tipo, count(*) AS totale;


// ----------------------------------------------------------------------------
// STEP 7 — QUERY DI TEST (esegui per verificare integrità)
// ----------------------------------------------------------------------------

// Test 1: Disease con più evidenze
MATCH (e:Evidence)-[:HAS_DISEASE]->(d:Disease)
RETURN d.name AS disease, d.doid AS doid, count(e) AS n_evidenze
ORDER BY n_evidenze DESC LIMIT 10;

// Test 2: Publication più citata
MATCH (e:Evidence)-[:CITED_IN]->(p:Publication)
RETURN p.pmid AS pmid, p.citation_text AS citazione, count(e) AS n_evidenze
ORDER BY n_evidenze DESC LIMIT 10;

// Test 3: Percorso completo Gene → Evidence → Disease → Publication
// (verifica che i nuovi nodi si integrino con lo schema esistente)
MATCH (g:Gene {hugo_symbol: 'EGFR'})
-[:HAS_VARIANT]->(:Variant)
-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
-[:HAS_EVIDENCE]->(e:Evidence)
-[:HAS_DISEASE]->(d:Disease)
MATCH (e)-[:CITED_IN]->(p:Publication)
WHERE e.evidence_level = 'A'
RETURN g.hugo_symbol AS gene,
       d.name AS disease,
       d.doid AS doid,
       e.evidence_level AS livello,
       p.pmid AS pmid,
       p.citation_text AS citazione
ORDER BY d.name LIMIT 10;

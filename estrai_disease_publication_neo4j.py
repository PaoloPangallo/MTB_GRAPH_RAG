"""
Script: estrai_disease_publication_neo4j.py
Scopo:  Estrae i nodi Disease e Publication dal file TSV CIViC
        (nightly-AcceptedClinicalEvidenceSummaries.tsv) e genera:
        
        1. CSV pronti per il caricamento in Neo4j:
           - civic_diseases.csv
           - civic_publications.csv
           - civic_evidence_disease_links.csv   (archi HAS_DISEASE)
           - civic_evidence_publication_links.csv (archi CITED_IN)
        
        2. Script Cypher completo per:
           - Creare constraint e indici
           - Caricare i nodi Disease e Publication
           - Creare gli archi verso Evidence

Statistiche attese dal file nightly (31 maggio 2026):
  - Disease uniche: 335 (302 con DOID, 33 senza)
  - Publication uniche: 2234
  - Evidence totali: 4855

Uso:
  python estrai_disease_publication_neo4j.py

Output directory: stessa cartella dello script
"""

import pandas as pd
import os
from pathlib import Path

# ============================================================================
# CONFIGURAZIONE — modifica questi path
# ============================================================================

# Path del TSV CIViC scaricato
INPUT_TSV = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI\Civic\01-May-2026-AcceptedClinicalEvidenceSummaries.tsv"

# Cartella di output per i CSV e lo script Cypher
OUTPUT_DIR = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI\Clean_Graph_Data")

# ============================================================================
# CARICAMENTO TSV
# ============================================================================

print("=" * 60)
print("ESTRAZIONE NODI DISEASE E PUBLICATION DA CIViC TSV")
print("=" * 60)

print(f"\n[1/6] Caricamento TSV: {INPUT_TSV}")
df = pd.read_csv(INPUT_TSV, sep="\t", dtype=str)
df["evidence_id"] = pd.to_numeric(df["evidence_id"], errors="coerce")
df["doid"] = pd.to_numeric(df["doid"], errors="coerce")
df["citation_id"] = pd.to_numeric(df["citation_id"], errors="coerce")
print(f"  Righe caricate: {len(df):,}")
print(f"  Colonne: {list(df.columns)}")

# ============================================================================
# ESTRAZIONE NODI DISEASE
# ============================================================================

print(f"\n[2/6] Estrazione nodi Disease...")

diseases = (
    df[["disease", "doid"]]
    .dropna(subset=["disease"])
    .drop_duplicates(subset=["disease"])
    .copy()
)

# Normalizza DOID — converti a intero dove possibile
diseases["doid"] = diseases["doid"].apply(
    lambda x: int(x) if pd.notna(x) else ""
)

# Aggiungi disease_id progressivo
diseases = diseases.reset_index(drop=True)
diseases.insert(0, "disease_id", range(1, len(diseases) + 1))

# Aggiungi colonna doid_uri per ontologia formale
diseases["doid_uri"] = diseases["doid"].apply(
    lambda x: f"http://purl.obolibrary.org/obo/DOID_{x}" if x != "" else ""
)

print(f"  Disease uniche trovate: {len(diseases):,}")
print(f"  Con DOID: {(diseases['doid'] != '').sum():,}")
print(f"  Senza DOID: {(diseases['doid'] == '').sum():,}")
print(f"  Esempio:")
print(diseases.head(3).to_string(index=False))

# Salva CSV
disease_csv = OUTPUT_DIR / "civic_diseases.csv"
diseases.to_csv(disease_csv, index=False, encoding="utf-8")
print(f"  Salvato: {disease_csv}")

# ============================================================================
# ESTRAZIONE NODI PUBLICATION
# ============================================================================

print(f"\n[3/6] Estrazione nodi Publication...")

publications = (
    df[["citation_id", "source_type", "citation", "asco_abstract_id"]]
    .dropna(subset=["citation_id"])
    .drop_duplicates(subset=["citation_id"])
    .copy()
)

# Rinomina colonne per chiarezza in Neo4j
publications = publications.rename(columns={
    "citation_id": "pmid",
    "source_type": "source_type",
    "citation": "citation_text",
    "asco_abstract_id": "asco_abstract_id"
})

# Estrai anno dalla citation (es. "Levine et al., 2005" → 2005)
publications["year"] = publications["citation_text"].str.extract(r"(\d{4})")

# Aggiungi URL PubMed dove disponibile
publications["pubmed_url"] = publications.apply(
    lambda r: f"https://pubmed.ncbi.nlm.nih.gov/{int(r['pmid'])}"
    if r["source_type"] == "PubMed" and pd.notna(r["pmid"]) else "",
    axis=1
)

# Pulisci pmid come intero
publications["pmid"] = publications["pmid"].apply(
    lambda x: int(x) if pd.notna(x) else ""
)

print(f"  Publication uniche trovate: {len(publications):,}")
print(f"  Source types:")
print(df["source_type"].value_counts().to_string())
print(f"  Esempio:")
print(publications.head(3).to_string(index=False))

# Salva CSV
pub_csv = OUTPUT_DIR / "civic_publications.csv"
publications.to_csv(pub_csv, index=False, encoding="utf-8")
print(f"  Salvato: {pub_csv}")

# ============================================================================
# ESTRAZIONE ARCHI Evidence -> Disease (HAS_DISEASE)
# ============================================================================

print(f"\n[4/6] Estrazione archi Evidence -> Disease...")

# Mappa disease_name → disease_id
disease_map = dict(zip(diseases["disease"], diseases["disease_id"]))

evidence_disease = (
    df[["evidence_id", "disease"]]
    .dropna(subset=["evidence_id", "disease"])
    .copy()
)
evidence_disease["disease_id"] = evidence_disease["disease"].map(disease_map)
evidence_disease = evidence_disease[["evidence_id", "disease_id"]].dropna()
evidence_disease["evidence_id"] = evidence_disease["evidence_id"].astype(int)
evidence_disease["disease_id"] = evidence_disease["disease_id"].astype(int)

print(f"  Archi HAS_DISEASE: {len(evidence_disease):,}")

ed_csv = OUTPUT_DIR / "civic_evidence_disease_links.csv"
evidence_disease.to_csv(ed_csv, index=False, encoding="utf-8")
print(f"  Salvato: {ed_csv}")

# ============================================================================
# ESTRAZIONE ARCHI Evidence -> Publication (CITED_IN)
# ============================================================================

print(f"\n[5/6] Estrazione archi Evidence -> Publication...")

evidence_pub = (
    df[["evidence_id", "citation_id"]]
    .dropna(subset=["evidence_id", "citation_id"])
    .copy()
)
evidence_pub = evidence_pub.rename(columns={"citation_id": "pmid"})
evidence_pub["evidence_id"] = evidence_pub["evidence_id"].astype(int)
evidence_pub["pmid"] = evidence_pub["pmid"].astype(int)

print(f"  Archi CITED_IN: {len(evidence_pub):,}")

ep_csv = OUTPUT_DIR / "civic_evidence_publication_links.csv"
evidence_pub.to_csv(ep_csv, index=False, encoding="utf-8")
print(f"  Salvato: {ep_csv}")

# ============================================================================
# GENERAZIONE SCRIPT CYPHER
# ============================================================================

print(f"\n[6/6] Generazione script Cypher...")

cypher_script = """
// ============================================================================
// CARICAMENTO NODI DISEASE E PUBLICATION IN NEO4J
// Script generato automaticamente da estrai_disease_publication_neo4j.py
// Data: {date}
// 
// PREREQUISITI:
//   1. Neo4j Desktop aperto con il database GraphRAGTesi attivo
//   2. I 4 file CSV nella cartella Neo4j import:
//      {neo4j_import}/civic_diseases.csv
//      {neo4j_import}/civic_publications.csv
//      {neo4j_import}/civic_evidence_disease_links.csv
//      {neo4j_import}/civic_evidence_publication_links.csv
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
"""
cypher_script = cypher_script.replace("{date}", pd.Timestamp.now().strftime("%Y-%m-%d"))
cypher_script = cypher_script.replace("{neo4j_import}", r"C:\Users\paolo\Neo4jDesktop2\Data\dbms\dbms-c1022817-b4f0-4d0d-a4ec-ee39e0dff0c9\import")

cypher_path = OUTPUT_DIR / "carica_disease_publication.cypher"
cypher_path.write_text(cypher_script, encoding="utf-8")
print(f"  Salvato: {cypher_path}")

# ============================================================================
# RIEPILOGO FINALE
# ============================================================================

print()
print("=" * 60)
print("RIEPILOGO FINALE")
print("=" * 60)
print(f"  civic_diseases.csv              -> {len(diseases):>5} righe")
print(f"  civic_publications.csv          -> {len(publications):>5} righe")
print(f"  civic_evidence_disease_links    -> {len(evidence_disease):>5} righe")
print(f"  civic_evidence_publication_links-> {len(evidence_pub):>5} righe")
print()
print("PROSSIMI PASSI:")
print("  1. Copia i 4 CSV nella cartella import di Neo4j:")
print(f"     {r'C:\Users\paolo\Neo4jDesktop2\Data\dbms\dbms-c1022817-b4f0-4d0d-a4ec-ee39e0dff0c9\import'}")
print("  2. Apri Neo4j Browser (GraphRAGTesi)")
print("  3. Esegui carica_disease_publication.cypher step per step")
print("  4. Verifica con le query di test in STEP 6 e 7")
print()
print("SCHEMA AGGIORNATO DOPO IL CARICAMENTO:")
print("  Evidence -[:HAS_DISEASE]-> Disease")
print("  Evidence -[:CITED_IN]-> Publication")
print("  (si integrano con gli archi esistenti)")
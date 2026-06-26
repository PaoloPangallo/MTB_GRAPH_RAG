"""
Tutte le costanti Cypher in un unico file.
Se una query va corretta, tocchi un file solo.

Nomenclatura:
  PRE_*         → pre-query per il Complexity Check
  VARIANT_*     → Variant Interpreter
  TARGET_*      → Target Identifier
  TRIALS        → Trial Matcher
  RESISTANCE_*  → Resistance Checker
  VERIFY_PMIDS  → Synthesizer
"""

# ─────────────────────────────────────────────
# COMPLEXITY CHECK — pre-query
# ─────────────────────────────────────────────

CYPHER_PRE_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
WITH count(e) AS n_evidence,
     collect(DISTINCT e.significance) AS significances
OPTIONAL MATCH (ct:ClinicalTrial)-[:ASSOCIATED_GENE]->(g2:Gene {hugo_symbol: $gene})
WHERE ANY(c IN ct.conditions WHERE ANY(kw IN $disease_keywords WHERE toLower(c) CONTAINS kw))
WITH n_evidence, significances, count(ct) AS n_trials
RETURN n_evidence, significances, n_trials
"""

CYPHER_PRE_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
WITH count(e) AS n_evidence,
     collect(DISTINCT e.significance) AS significances
RETURN n_evidence, significances, 0 AS n_trials
"""

CYPHER_PRE_BIOMARKER = """
MATCH (mp:MolecularProfile)
WHERE toLower(replace(mp.name, "-", " ")) = toLower(replace($mp_name, "-", " "))
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
WITH count(e) AS n_evidence,
     collect(DISTINCT e.significance) AS significances
RETURN n_evidence, significances, 0 AS n_trials
"""

# ─────────────────────────────────────────────
# VARIANT INTERPRETER
# ─────────────────────────────────────────────

# Percorso classico (point_mutation, itd)
CYPHER_VARIANT_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:CITED_IN]->(p:Publication)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
RETURN e.evidence_level     AS evidence_level,
       e.significance       AS significance,
       e.disease            AS disease,
       p.pmid               AS pmid,
       p.citation_text      AS citation_text,
       mp.name              AS molecular_profile
ORDER BY e.evidence_level ASC, size(mp.name) ASC
LIMIT 15
"""

# Percorso MolecularProfile (fusion, cna, atypical)
CYPHER_VARIANT_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene_keyword)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
     -[:CITED_IN]->(p:Publication)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
RETURN e.evidence_level     AS evidence_level,
       e.significance       AS significance,
       e.disease            AS disease,
       p.pmid               AS pmid,
       p.citation_text      AS citation_text,
       mp.name              AS molecular_profile
ORDER BY e.evidence_level ASC, size(mp.name) ASC
LIMIT 15
"""

# Biomarker senza gene (MSI High, TMB High)
CYPHER_VARIANT_BIOMARKER = """
MATCH (mp:MolecularProfile)
WHERE toLower(replace(mp.name, "-", " ")) = toLower(replace($mp_name, "-", " "))
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
     -[:CITED_IN]->(p:Publication)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
RETURN e.evidence_level     AS evidence_level,
       e.significance       AS significance,
       e.disease            AS disease,
       p.pmid               AS pmid,
       p.citation_text      AS citation_text,
       mp.name              AS molecular_profile
ORDER BY e.evidence_level ASC
LIMIT 15
"""

# ─────────────────────────────────────────────
# TARGET IDENTIFIER
# ─────────────────────────────────────────────

CYPHER_TARGET_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND e.significance = 'Sensitivity/Response'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (d)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN d.drug_name       AS drug_name,
       d.approved        AS approved,
       cd.device_name    AS companion_diagnostic,
       cd.platform_type  AS cd_platform,
       e.evidence_level  AS evidence_level
ORDER BY e.evidence_level ASC
"""

CYPHER_TARGET_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene_keyword)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
         -[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND e.significance = 'Sensitivity/Response'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (d)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN d.drug_name       AS drug_name,
       d.approved        AS approved,
       cd.device_name    AS companion_diagnostic,
       cd.platform_type  AS cd_platform,
       e.evidence_level  AS evidence_level
ORDER BY e.evidence_level ASC, size(mp.name) ASC
"""

CYPHER_TARGET_BIOMARKER = """
MATCH (mp:MolecularProfile)
WHERE toLower(replace(mp.name, "-", " ")) = toLower(replace($mp_name, "-", " "))
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
         -[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND e.significance = 'Sensitivity/Response'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (d)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN d.drug_name       AS drug_name,
       d.approved        AS approved,
       cd.device_name    AS companion_diagnostic,
       cd.platform_type  AS cd_platform,
       e.evidence_level  AS evidence_level
ORDER BY e.evidence_level ASC
"""

# ─────────────────────────────────────────────
# TRIAL MATCHER
# ─────────────────────────────────────────────

CYPHER_TRIALS = """
MATCH (ct:ClinicalTrial)-[:ASSOCIATED_GENE]->(g:Gene {hugo_symbol: $gene})
WHERE ANY(c IN ct.conditions WHERE ANY(kw IN $disease_keywords WHERE toLower(c) CONTAINS kw))
   OR ANY(k IN ct.keywords   WHERE ANY(kw IN $disease_keywords WHERE toLower(k) CONTAINS kw))
OPTIONAL MATCH (ct)-[:TESTS_DRUG]->(d:Drug)
WHERE d.drug_name IN $drug_names
RETURN ct.nct_id     AS nct_id,
       ct.title      AS title,
       ct.phase      AS phase,
       ct.status     AS status,
       d.drug_name   AS drug_tested
ORDER BY ct.phase DESC
LIMIT 5
"""

# ─────────────────────────────────────────────
# RESISTANCE CHECKER
# ─────────────────────────────────────────────

CYPHER_RESISTANCE_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:CITED_IN]->(p:Publication)
WHERE e.significance = 'Resistance'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
  AND e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
RETURN v.variant_name        AS variant,
       e.evidence_level      AS evidence_level,
       e.disease             AS disease,
       e.evidence_statement  AS statement,
       p.pmid                AS pmid,
       p.citation_text       AS citation_text,
       d.drug_name           AS drug_name
ORDER BY e.evidence_level ASC
LIMIT 5
"""

CYPHER_RESISTANCE_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene_keyword)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
         -[:CITED_IN]->(p:Publication)
WHERE e.significance = 'Resistance'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
  AND e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
RETURN mp.name               AS variant,
       e.evidence_level      AS evidence_level,
       e.disease             AS disease,
       e.evidence_statement  AS statement,
       p.pmid                AS pmid,
       p.citation_text       AS citation_text,
       d.drug_name           AS drug_name
ORDER BY e.evidence_level ASC
LIMIT 5
"""

CYPHER_RESISTANCE_BIOMARKER = """
MATCH (mp:MolecularProfile)
WHERE toLower(replace(mp.name, "-", " ")) = toLower(replace($mp_name, "-", " "))
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
         -[:CITED_IN]->(p:Publication)
WHERE e.significance = 'Resistance'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
  AND e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
RETURN mp.name               AS variant,
       e.evidence_level      AS evidence_level,
       e.disease             AS disease,
       e.evidence_statement  AS statement,
       p.pmid                AS pmid,
       p.citation_text       AS citation_text,
       d.drug_name           AS drug_name
ORDER BY e.evidence_level ASC
LIMIT 5
"""

CYPHER_RESISTANCE_GENE = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant)
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:CITED_IN]->(p:Publication)
WHERE e.significance = 'Resistance'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
  AND e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
RETURN DISTINCT v.variant_name AS variant,
                e.evidence_level AS evidence_level,
                e.disease        AS disease,
                e.evidence_statement AS statement,
                p.pmid           AS pmid,
                p.citation_text  AS citation_text,
                d.drug_name      AS drug_name
ORDER BY e.evidence_level ASC, v.variant_name ASC
LIMIT 15
"""

CYPHER_EXCLUDE_DRUGS = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v_driver:Variant)
      -[:IN_MOLECULAR_PROFILE]->(mp_driver:MolecularProfile)
WHERE toLower(mp_driver.name) CONTAINS toLower($driver_variant)
MATCH (mp_driver)-[:HAS_EVIDENCE]->(e_driver:Evidence {significance: 'Sensitivity/Response'})
      -[:TARGETS_DRUG]->(d:Drug)
WHERE e_driver.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e_driver.disease) CONTAINS kw)
WITH DISTINCT d.drug_name AS drug_name

OPTIONAL MATCH (mp_curr:MolecularProfile)-[:HAS_EVIDENCE]->(e_curr:Evidence {significance: 'Sensitivity/Response'})-[:TARGETS_DRUG]->(d_curr:Drug {drug_name: drug_name})
WHERE toLower(mp_curr.name) CONTAINS toLower($gene)
  AND toLower(mp_curr.name) CONTAINS toLower($variant)
  AND e_curr.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
  AND ANY(kw IN $disease_keywords WHERE toLower(e_curr.disease) CONTAINS kw)
  
WITH drug_name, count(d_curr) AS sensitivity_matches
WHERE sensitivity_matches = 0
RETURN collect(DISTINCT drug_name) AS exclude_drugs
"""


# ─────────────────────────────────────────────
# SYNTHESIZER — verifica PMID
# ─────────────────────────────────────────────

CYPHER_VERIFY_PMIDS = """
MATCH (e:Evidence)-[:CITED_IN]->(p:Publication)
WHERE p.pmid IN $pmids
  AND e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
RETURN DISTINCT p.pmid          AS pmid,
                p.citation_text AS citation_text
"""

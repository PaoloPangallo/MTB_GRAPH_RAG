"""
Estrazione del sotto-grafo Neo4j attivato per un caso clinico.

Espone:
  - extract_subgraph(gene, variant, tumor_type, alteration_type)
    → { nodes: [...], links: [...] }
  - build_zeroshot_subgraph(cited_pmids)
    → grafo sintetico per visualizzare l'allucinazione zero-shot
"""

from __future__ import annotations

from backend.pipeline.helpers import run_cypher, get_disease_keywords, get_mp_keyword


# ── Colori per tipo nodo ────────────────────────────────────

NODE_COLORS = {
    "gene":                  "#0EA5E9",
    "variant":               "#8B5CF6",
    "molecular_profile":     "#1E3A8A",
    "drug":                  "#10B981",
    "evidence":              "#F59E0B",
    "publication":           "#D97706",
    "clinical_trial":        "#7C3AED",
    "companion_diagnostic":  "#06B6D4",
    "resistance":            "#EF4444",
    "llm_memory":            "#A21CAF",
}

# Peso visivo (dimensione nodo nel grafo)
NODE_SIZES = {
    "gene": 12,
    "variant": 10,
    "molecular_profile": 14,
    "drug": 8,
    "evidence": 6,
    "publication": 5,
    "clinical_trial": 7,
    "companion_diagnostic": 5,
    "resistance": 8,
    "llm_memory": 14,
}


# ── Query Cypher unificata per sotto-grafo ──────────────────

CYPHER_SUBGRAPH_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.evidence_level IN ['A', 'B']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (e)-[:CITED_IN]->(p:Publication)
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
OPTIONAL MATCH (d)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN g.hugo_symbol       AS gene_symbol,
       v.variant_name      AS variant_name,
       mp.name             AS mp_name,
       e.evidence_level    AS evidence_level,
       e.significance      AS significance,
       e.disease           AS disease,
       e.evidence_statement AS statement,
       p.pmid              AS pmid,
       p.citation_text     AS citation_text,
       d.drug_name         AS drug_name,
       d.approved          AS drug_approved,
       cd.device_name      AS cd_name,
       cd.platform_type    AS cd_platform
ORDER BY e.evidence_level ASC
LIMIT 40
"""

CYPHER_SUBGRAPH_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene_keyword)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.evidence_level IN ['A', 'B']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (e)-[:CITED_IN]->(p:Publication)
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
OPTIONAL MATCH (d)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN NULL               AS gene_symbol,
       NULL               AS variant_name,
       mp.name            AS mp_name,
       e.evidence_level   AS evidence_level,
       e.significance     AS significance,
       e.disease          AS disease,
       e.evidence_statement AS statement,
       p.pmid             AS pmid,
       p.citation_text    AS citation_text,
       d.drug_name        AS drug_name,
       d.approved         AS drug_approved,
       cd.device_name     AS cd_name,
       cd.platform_type   AS cd_platform
ORDER BY e.evidence_level ASC
LIMIT 40
"""

CYPHER_SUBGRAPH_TRIALS = """
MATCH (ct:ClinicalTrial)-[:ASSOCIATED_GENE]->(g:Gene {hugo_symbol: $gene})
WHERE ANY(c IN ct.conditions WHERE ANY(kw IN $disease_keywords WHERE toLower(c) CONTAINS kw))
OPTIONAL MATCH (ct)-[:TESTS_DRUG]->(d:Drug)
RETURN ct.nct_id   AS nct_id,
       ct.title    AS title,
       ct.phase    AS phase,
       ct.status   AS status,
       d.drug_name AS drug_tested
ORDER BY ct.phase DESC
LIMIT 5
"""

CYPHER_SUBGRAPH_RESISTANCE = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant)
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.significance = 'Resistance'
  AND e.evidence_level IN ['A', 'B']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
RETURN DISTINCT v.variant_name AS variant_name,
                e.evidence_level AS evidence_level,
                e.disease AS disease,
                d.drug_name AS drug_name
ORDER BY e.evidence_level ASC
LIMIT 10
"""


def _make_node(id: str, label: str, ntype: str, metadata: dict | None = None) -> dict:
    """Crea un nodo con id, label, tipo, colore e metadata."""
    return {
        "id": id,
        "label": label,
        "type": ntype,
        "color": NODE_COLORS.get(ntype, "#94A3B8"),
        "val": NODE_SIZES.get(ntype, 6),
        "metadata": metadata or {},
    }


def _make_link(source: str, target: str, label: str, link_type: str = "") -> dict:
    """Crea un link tra due nodi."""
    return {
        "source": source,
        "target": target,
        "label": label,
        "type": link_type or label,
    }


def extract_subgraph(
    gene: str,
    variant: str,
    tumor_type: str,
    alteration_type: str = "point_mutation",
) -> dict:
    """Estrae il sotto-grafo reale da Neo4j per un caso clinico."""

    disease_keywords = get_disease_keywords(tumor_type)
    nodes_map: dict[str, dict] = {}
    links: list[dict] = []

    # ── Determina quale query usare ────────────────────────
    use_mp_path = alteration_type in ("fusion", "cna", "atypical")

    if use_mp_path:
        mp_keyword = get_mp_keyword(alteration_type, variant)
        records = run_cypher(CYPHER_SUBGRAPH_MP, {
            "gene_keyword": gene,
            "mp_keyword": mp_keyword,
            "disease_keywords": disease_keywords,
        })
    else:
        records = run_cypher(CYPHER_SUBGRAPH_POINT, {
            "gene": gene,
            "variant": variant,
            "disease_keywords": disease_keywords,
        })

    # ── Processa i record ──────────────────────────────────
    for rec in records:
        # Gene node
        gene_sym = rec.get("gene_symbol")
        if gene_sym:
            gid = f"gene_{gene_sym}"
            if gid not in nodes_map:
                nodes_map[gid] = _make_node(gid, gene_sym, "gene", {"hugo_symbol": gene_sym})

        # Variant node
        var_name = rec.get("variant_name")
        if var_name:
            vid = f"var_{var_name}"
            if vid not in nodes_map:
                nodes_map[vid] = _make_node(vid, var_name, "variant", {"variant_name": var_name})
            if gene_sym:
                links.append(_make_link(f"gene_{gene_sym}", vid, "HAS_VARIANT"))

        # MolecularProfile node
        mp_name = rec.get("mp_name")
        if mp_name:
            mpid = f"mp_{mp_name[:50]}"
            if mpid not in nodes_map:
                nodes_map[mpid] = _make_node(mpid, mp_name, "molecular_profile", {"name": mp_name})
            if var_name:
                links.append(_make_link(f"var_{var_name}", mpid, "IN_MOLECULAR_PROFILE"))
            elif not use_mp_path and gene_sym:
                links.append(_make_link(f"gene_{gene_sym}", mpid, "HAS_PROFILE"))

        # Evidence node
        ev_level = rec.get("evidence_level", "")
        significance = rec.get("significance", "")
        disease = rec.get("disease", "")
        statement = rec.get("statement", "")
        ev_id = f"ev_{ev_level}_{significance}_{disease}"[:60]
        if ev_id not in nodes_map:
            ev_label = f"{significance} ({ev_level})"
            ntype = "resistance" if significance == "Resistance" else "evidence"
            nodes_map[ev_id] = _make_node(ev_id, ev_label, ntype, {
                "evidence_level": ev_level,
                "significance": significance,
                "disease": disease,
                "statement": statement,
            })
        if mp_name:
            links.append(_make_link(f"mp_{mp_name[:50]}", ev_id, "HAS_EVIDENCE"))

        # Publication node
        pmid = rec.get("pmid")
        if pmid:
            pid = f"pmid_{pmid}"
            if pid not in nodes_map:
                citation = rec.get("citation_text", "")
                nodes_map[pid] = _make_node(pid, f"PMID: {pmid}", "publication", {
                    "pmid": pmid,
                    "citation_text": citation,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}",
                })
            links.append(_make_link(ev_id, pid, "CITED_IN"))

        # Drug node
        drug_name = rec.get("drug_name")
        if drug_name:
            did = f"drug_{drug_name}"
            if did not in nodes_map:
                nodes_map[did] = _make_node(did, drug_name, "drug", {
                    "drug_name": drug_name,
                    "approved": rec.get("drug_approved"),
                })
            links.append(_make_link(ev_id, did, "TARGETS_DRUG"))

            # CompanionDiagnostic node
            cd_name = rec.get("cd_name")
            if cd_name:
                cdid = f"cd_{cd_name}"
                if cdid not in nodes_map:
                    nodes_map[cdid] = _make_node(cdid, cd_name, "companion_diagnostic", {
                        "device_name": cd_name,
                        "platform_type": rec.get("cd_platform", ""),
                    })
                links.append(_make_link(did, cdid, "HAS_COMPANION_DIAGNOSTIC"))

    # ── Clinical Trials ────────────────────────────────────
    if gene:
        drug_names = [n["label"] for n in nodes_map.values() if n["type"] == "drug"]
        trial_records = run_cypher(CYPHER_SUBGRAPH_TRIALS, {
            "gene": gene,
            "disease_keywords": disease_keywords,
            "drug_names": drug_names or ["__none__"],
        })
        for tr in trial_records:
            nct = tr.get("nct_id")
            if not nct:
                continue
            tid = f"trial_{nct}"
            if tid not in nodes_map:
                nodes_map[tid] = _make_node(tid, nct, "clinical_trial", {
                    "nct_id": nct,
                    "title": tr.get("title", ""),
                    "phase": tr.get("phase", ""),
                    "status": tr.get("status", ""),
                    "url": f"https://clinicaltrials.gov/ct2/show/{nct}",
                })
            # Link trial al gene
            gid = f"gene_{gene}"
            if gid in nodes_map:
                links.append(_make_link(gid, tid, "ASSOCIATED_GENE"))
            # Link trial al farmaco testato
            drug_tested = tr.get("drug_tested")
            if drug_tested and f"drug_{drug_tested}" in nodes_map:
                links.append(_make_link(tid, f"drug_{drug_tested}", "TESTS_DRUG"))

    # ── Resistance sub-graph ───────────────────────────────
    if gene:
        res_records = run_cypher(CYPHER_SUBGRAPH_RESISTANCE, {
            "gene": gene,
            "disease_keywords": disease_keywords,
        })
        for rr in res_records:
            rv = rr.get("variant_name")
            if not rv:
                continue
            rid = f"res_{rv}"
            if rid not in nodes_map:
                nodes_map[rid] = _make_node(rid, rv, "resistance", {
                    "variant_name": rv,
                    "evidence_level": rr.get("evidence_level", ""),
                    "disease": rr.get("disease", ""),
                })
            gid = f"gene_{gene}"
            if gid in nodes_map:
                links.append(_make_link(gid, rid, "RESISTANCE_VARIANT"))
            # Link alla drug se presente
            rd = rr.get("drug_name")
            if rd and f"drug_{rd}" in nodes_map:
                links.append(_make_link(rid, f"drug_{rd}", "RESISTS_DRUG"))

    # ── Deduplica link ─────────────────────────────────────
    seen_links: set[str] = set()
    unique_links: list[dict] = []
    for link in links:
        key = f"{link['source']}|{link['target']}|{link['label']}"
        if key not in seen_links:
            seen_links.add(key)
            unique_links.append(link)

    return {
        "nodes": list(nodes_map.values()),
        "links": unique_links,
    }


def build_zeroshot_subgraph(cited_pmids: list[int]) -> dict:
    """Costruisce un grafo sintetico per visualizzare l'allucinazione zero-shot."""
    nodes = [
        _make_node("llm_core", "LLM Parametric Memory", "llm_memory", {
            "description": "Memoria interna del Large Language Model. "
                           "Nessun database consultato.",
        }),
    ]
    links = []

    for i, pmid in enumerate(cited_pmids[:8]):
        pid = f"halluc_pmid_{i}"
        nodes.append(_make_node(pid, f"PMID: {pmid}", "publication", {
            "pmid": pmid,
            "hallucinated": True,
            "description": "PMID citato dall'LLM ma NON verificato nel Knowledge Graph. "
                           "Con alta probabilità è un'allucinazione.",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}",
        }))
        links.append(_make_link("llm_core", pid, "HALLUCINATED", "HALLUCINATED"))

    return {"nodes": nodes, "links": links}

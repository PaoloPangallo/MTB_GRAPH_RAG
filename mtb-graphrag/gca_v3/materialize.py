"""Materializzatore v3 — rimaterializza dai CSV sorgente.

**Non** converte ``candidates.jsonl`` v2. La conversione da v2 non potrebbe
recuperare ciò che v2 ha perso: le varianti scartate e la polarità non sono più
nell'artefatto. La rimaterializzazione parte quindi dall'export originale.

Differenze rispetto alla regola v2, tutte giustificate dall'audit:

``evidence-statement``
    conserva l'espressione di alterazione completa (AST) invece della prima
    variante, e separa direzione del grafo da posizione della fonte.

``evidence-to-drug``
    **una candidate per record Evidence**, non una per arco farmaco. Un record
    con più farmaci produce una sola candidate a livello di regime, marcata
    ``MULTI_COMPONENT_UNRESOLVED``. Questo elimina lo split che attribuiva la
    stessa direzione a ciascun farmaco individualmente.

Le regole ``gene-drug-interaction``, ``companion-diagnostic``, ``trial-drug`` e
``trial-gene`` restano invariate nella struttura; acquistano i campi v3 con i
valori che la sorgente consente (tipicamente `UNKNOWN`/`NOT_REPORTED`).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from evaluation.rq1.kg_source import FrozenKnowledgeGraph, _clean, _typed

from .alterations import MISSING, parse_alteration_expression
from .contract import GraphCandidateAssertionV3
from .polarity import (
    GRAPH_DIRECTION_UNKNOWN, NOT_REPORTED, SOURCE_ALIGNMENT_NOT_AVAILABLE, describe,
)
from .regimens import (
    NOT_APPLICABLE, STRUCTURE_UNKNOWN, build_intervention,
)

MATERIALIZER_VERSION = "gca-materializer/3.0"

#: Regole v3. Gli identificatori sono versionati perché la semantica è cambiata:
#: ``evidence-to-drug`` non è più per-arco ma **per record Evidence**, e
#: ``evidence-statement`` conserva l'espressione di alterazione completa. Riusare
#: gli id ``gca/2.0/*`` farebbe passare per identiche regole che non lo sono.
RULE_EVIDENCE_STATEMENT = "gca/3.0/evidence-statement"
RULE_EVIDENCE_TO_DRUG = "gca/3.0/evidence-to-intervention"
RULE_GENE_DRUG = "gca/3.0/gene-drug-interaction"
RULE_COMPANION_DIAGNOSTIC = "gca/3.0/companion-diagnostic"
RULE_TRIAL_DRUG = "gca/3.0/trial-drug"
RULE_TRIAL_GENE = "gca/3.0/trial-gene"

#: Corrispondenza con le regole v2, per il mapping di migrazione.
V2_RULE_BY_V3_RULE = {
    RULE_EVIDENCE_STATEMENT: "gca/2.0/evidence-statement",
    RULE_EVIDENCE_TO_DRUG: "gca/2.0/evidence-to-drug",
    RULE_GENE_DRUG: "gca/2.0/gene-drug-interaction",
    RULE_COMPANION_DIAGNOSTIC: "gca/2.0/companion-diagnostic",
    RULE_TRIAL_DRUG: "gca/2.0/trial-drug",
    RULE_TRIAL_GENE: "gca/2.0/trial-gene",
}

NULL_TOKENS = {"", "nan", "none", "null"}


class MaterializerV3:
    """Costruisce il repository v3 dall'export congelato."""

    def __init__(self, graph: FrozenKnowledgeGraph, materialized_at: str = "2026-08-06T00:00:00Z"):
        self.graph = graph
        self.materialized_at = materialized_at

        self.evidence = graph.node_index("node_evidence.csv")
        self.profiles = graph.node_index("node_molecular_profile.csv")
        self.variants = graph.node_index("node_variant.csv")
        self.genes = graph.node_index("node_gene.csv")
        self.drugs = graph.node_index("node_drug.csv")
        self.diseases = graph.node_index("civic_diseases.csv")
        self.devices = graph.node_index("node_companion_diagnostic.csv")

        self.pub_links = defaultdict(list)
        for edge_id, row in graph.edge_rows("civic_evidence_publication_links.csv"):
            self.pub_links[_clean(row.get("evidence_id"))].append((edge_id, row))
        self.disease_links = defaultdict(list)
        for edge_id, row in graph.edge_rows("civic_evidence_disease_links.csv"):
            self.disease_links[_clean(row.get("evidence_id"))].append((edge_id, row))
        self.profile_variants = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_in_molecular_profile.csv"):
            self.profile_variants[_clean(row.get("target_molecular_profile_id"))].append((edge_id, row))
        self.variant_genes = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_has_variant.csv"):
            self.variant_genes[_clean(row.get("target_variant_id"))].append((edge_id, row))
        self.drug_edges = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_targets_drug.csv"):
            self.drug_edges[_clean(row.get("source_evidence_id"))].append((edge_id, row))
        self.cdx_by_device = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_has_companion_diagnostic.csv"):
            self.cdx_by_device[_clean(row.get("target_device_id"))].append((edge_id, row))

        self.excluded: list[dict[str, Any]] = []

    # ------------------------------------------------------------- contesto

    def _documents(self, evidence_id: str, erow: dict) -> list[dict]:
        out: list[dict] = []
        pmid = _clean(erow.get("citation_id"))
        if pmid and pmid.lower() not in NULL_TOKENS:
            out.append({"pmid": pmid, "scope": "evidence_record"})
        for _, row in self.pub_links.get(evidence_id, []):
            pmid = _clean(row.get("pmid"))
            entry = {"pmid": pmid, "scope": "linked_publication"}
            if pmid and entry not in out:
                out.append(entry)
        return out

    def _disease(self, evidence_id: str, erow: dict) -> list[dict]:
        values: list[dict] = []
        raw = _clean(erow.get("disease"))
        doid = _clean(erow.get("doid"))
        if raw:
            values.append({"id": f"disease:label:{raw}", "label": raw,
                           "canonical_id": f"DOID:{doid}" if doid and doid != "nan" else None})
        for _, link in self.disease_links.get(evidence_id, []):
            did = _clean(link.get("disease_id"))
            drow = self.diseases.get(did, {})
            value = {"id": f"Disease:{did}", "label": drow.get("disease") or did,
                     "canonical_id": f"DOID:{drow.get('doid')}" if drow.get("doid") else None}
            if value not in values:
                values.append(value)
        return values

    def _alteration(self, profile_id: str, profile: dict) -> dict[str, Any]:
        """Espressione di alterazione completa, dal nome del profilo molecolare."""
        parsed = parse_alteration_expression(profile.get("name"))
        parsed.setdefault("alteration_canonical_expression", None)
        return parsed

    def _biomarkers(self, profile_id: str, parsed: dict[str, Any]) -> list[dict]:
        """Biomarcatori: **tutti** i termini dell'espressione, non il primo.

        I node id delle varianti provengono dagli archi del grafo; i termini
        provengono dall'espressione. L'audit ha verificato che i due insiemi
        hanno la stessa cardinalità su tutti i 197 profili composti.
        """
        out: list[dict] = []
        seen: set[str] = set()
        for term in parsed.get("alteration_terms") or []:
            gene = term.get("gene")
            if gene and gene not in seen:
                seen.add(gene)
                node = _typed(gene, "Gene")
                node["label"] = gene
                out.append(node)
        for _, row in self.profile_variants.get(profile_id, []):
            variant_id = _clean(row.get("source_variant_id"))
            vrow = self.variants.get(variant_id, {})
            if vrow:
                node = _typed(variant_id, "Variant")
                node["label"] = vrow.get("variant_name")
                out.append(node)
        return out

    # ---------------------------------------------------------------- regole

    def build(self) -> list[GraphCandidateAssertionV3]:
        candidates: list[GraphCandidateAssertionV3] = []
        candidates.extend(self._evidence_candidates())
        candidates.extend(self._gene_drug_candidates())
        candidates.extend(self._companion_diagnostic_candidates())
        candidates.extend(self._trial_candidates())
        return candidates

    def _evidence_candidates(self) -> list[GraphCandidateAssertionV3]:
        out: list[GraphCandidateAssertionV3] = []
        for edge_profile_id, profile_edge in self.graph.edge_rows("edge_has_evidence.csv"):
            profile_id = _clean(profile_edge.get("source_molecular_profile_id"))
            evidence_id = _clean(profile_edge.get("target_evidence_id"))
            erow = self.evidence.get(evidence_id)
            profile = self.profiles.get(profile_id)
            if not erow or not profile:
                self.excluded.append({"path_id": edge_profile_id,
                                      "reason": "MISSING_EVIDENCE_OR_PROFILE"})
                continue

            parsed = self._alteration(profile_id, profile)
            biomarkers = self._biomarkers(profile_id, parsed)
            disease = self._disease(evidence_id, erow)
            documents = self._documents(evidence_id, erow)

            pvars = self.profile_variants.get(profile_id, [])
            first_variant = _clean(pvars[0][1].get("source_variant_id")) if pvars else ""
            gene_links = self.variant_genes.get(first_variant, [])
            subject = _typed(first_variant or profile_id,
                             "Variant" if first_variant else "MolecularProfile")
            subject["label"] = (self.variants.get(first_variant, {}).get("variant_name")
                                or profile.get("name") or subject["label"])
            context_nodes = [subject["id"], f"MolecularProfile:{profile_id}",
                             f"Evidence:{evidence_id}"]
            context_edges = ([e for e, _ in pvars] + [e for e, _ in gene_links]
                             + [edge_profile_id])

            # ---- evidence-statement ----
            statement = _clean(erow.get("evidence_statement"))
            if statement:
                polarity = describe(erow.get("significance"), erow.get("evidence_direction"))
                out.append(GraphCandidateAssertionV3.from_parts(
                    materialization_rule_id=RULE_EVIDENCE_STATEMENT,
                    materialized_at=self.materialized_at,
                    subject=subject, predicate="has_evidence_statement",
                    object=_typed(evidence_id, "Evidence"), disease=disease,
                    **polarity,
                    **{k: parsed.get(k) for k in (
                        "alteration_expression_raw", "alteration_terms",
                        "alteration_expression_ast", "alteration_parse_status",
                        "alteration_expression_hash", "alteration_parse_warnings",
                        "alteration_canonical_expression")},
                    intervention_expression_raw=None, intervention_components=[],
                    intervention_structure=STRUCTURE_UNKNOWN,
                    regimen_semantics_status=NOT_APPLICABLE, regimen_id=None,
                    regimen_limitations=[],
                    biomarkers=biomarkers, evidence_scope=erow.get("evidence_type"),
                    diagnostic_scope=None,
                    graph_path=context_nodes, node_ids=context_nodes, edge_ids=context_edges,
                    evidence_record_ids=[f"evidence:{evidence_id}"],
                    document_identifiers=documents,
                    source_properties={"evidence": erow, "profile": profile},
                    source_path_ids=[f"{RULE_EVIDENCE_STATEMENT}#{edge_profile_id}"],
                    v2_candidate_ids=[], known_limitations=[],
                ))
            else:
                self.excluded.append({"path_id": f"evidence-statement:{evidence_id}",
                                      "reason": "EMPTY_EVIDENCE_STATEMENT"})

            # ---- evidence-to-drug: UNA candidate per record Evidence ----
            drug_rows = self.drug_edges.get(evidence_id, [])
            resolved = [(edge_id, row) for edge_id, row in drug_rows
                        if self.drugs.get(_clean(row.get("target_drug_concept_id")))]
            for edge_id, row in drug_rows:
                if not self.drugs.get(_clean(row.get("target_drug_concept_id"))):
                    self.excluded.append({"path_id": edge_id, "reason": "MISSING_DRUG_NODE"})
            if not resolved:
                continue

            intervention = build_intervention(
                evidence_id, [row for _, row in resolved], self.drugs)
            # La polarità è quella del record: gli archi fratelli coincidono
            # sempre (verificato nell'audit su tutti e 3 370 gli archi).
            edge_row = resolved[0][1]
            polarity = describe(
                edge_row.get("significance") or erow.get("significance"),
                edge_row.get("evidence_direction") or erow.get("evidence_direction"),
            )
            predicate = self._predicate(polarity["graph_direction"])
            object_node = self._intervention_object(intervention)
            drug_node_ids = [c["node_id"] for c in intervention["intervention_components"]]

            out.append(GraphCandidateAssertionV3.from_parts(
                materialization_rule_id=RULE_EVIDENCE_TO_DRUG,
                materialized_at=self.materialized_at,
                subject=subject, predicate=predicate, object=object_node, disease=disease,
                **polarity,
                **{k: parsed.get(k) for k in (
                    "alteration_expression_raw", "alteration_terms",
                    "alteration_expression_ast", "alteration_parse_status",
                    "alteration_expression_hash", "alteration_parse_warnings",
                    "alteration_canonical_expression")},
                **{k: intervention[k] for k in (
                    "intervention_expression_raw", "intervention_components",
                    "intervention_structure", "regimen_semantics_status",
                    "regimen_id", "regimen_limitations")},
                biomarkers=biomarkers, evidence_scope=erow.get("evidence_type"),
                diagnostic_scope=None,
                graph_path=context_nodes + drug_node_ids,
                node_ids=context_nodes + drug_node_ids,
                edge_ids=context_edges + [edge_id for edge_id, _ in resolved],
                evidence_record_ids=[f"evidence:{evidence_id}"],
                document_identifiers=documents,
                source_properties={"evidence": erow, "profile": profile,
                                   "target_edges": [row for _, row in resolved]},
                source_path_ids=[f"{RULE_EVIDENCE_TO_DRUG}#{edge_profile_id}#{edge_id}"
                                 for edge_id, _ in resolved],
                v2_candidate_ids=[],
                known_limitations=list(intervention["regimen_limitations"]),
            ))
        return out

    @staticmethod
    def _predicate(graph_direction: str) -> str:
        """Predicato derivato dalla **direzione**, non dalla polarità.

        La polarità resta in un campo proprio: un predicato che la incorporasse
        renderebbe di nuovo indistinguibili «sostiene una resistenza» e «non
        sostiene una resistenza».
        """
        return {
            "SENSITIVITY": "associated_with_sensitivity_to",
            "REDUCED_SENSITIVITY": "associated_with_reduced_sensitivity_to",
            "RESISTANCE": "associated_with_resistance_to",
            "ADVERSE_RESPONSE": "associated_with_adverse_response_to",
        }.get(graph_direction, "evidence_association_with")

    @staticmethod
    def _intervention_object(intervention: dict[str, Any]) -> dict[str, Any]:
        components = intervention["intervention_components"]
        if len(components) == 1:
            node = _typed(components[0]["concept_id"], "Drug")
            node["label"] = components[0]["name"]
            return node
        return {
            "id": intervention["regimen_id"],
            "type": "TherapeuticRegimen",
            "label": intervention["intervention_expression_raw"],
            "canonical_id": None,
        }

    # ------------------------------------------------- regole non-Evidence

    def _base_non_evidence(self) -> dict[str, Any]:
        """Campi v3 per le regole che non portano polarità né alterazioni."""
        return {
            "graph_direction": GRAPH_DIRECTION_UNKNOWN,
            "source_support_polarity": NOT_REPORTED,
            "source_supported_direction": None,
            "source_alignment_status": SOURCE_ALIGNMENT_NOT_AVAILABLE,
            "source_polarity_raw": {"significance": None, "evidence_direction": None},
            "alteration_expression_raw": None, "alteration_terms": [],
            "alteration_expression_ast": None, "alteration_parse_status": MISSING,
            "alteration_expression_hash": None, "alteration_parse_warnings": [],
            "alteration_canonical_expression": None,
        }

    def _gene_drug_candidates(self) -> list[GraphCandidateAssertionV3]:
        out = []
        for edge_id, row in self.graph.edge_rows("edge_interacts_with.csv"):
            gene_id = _clean(row.get("source_gene_entrez_id"))
            drug_id = _clean(row.get("target_drug_concept_id"))
            if not (gene_id and drug_id):
                self.excluded.append({"path_id": edge_id, "reason": "MISSING_INTERACTION_ENDPOINT"})
                continue
            gene = _typed(gene_id, "Gene")
            gene["label"] = self.genes.get(gene_id, {}).get("hugo_symbol") or gene_id
            drug_row = self.drugs.get(drug_id, {})
            drug = _typed(drug_id, "Drug")
            drug["label"] = drug_row.get("drug_name") or drug_id
            out.append(GraphCandidateAssertionV3.from_parts(
                materialization_rule_id=RULE_GENE_DRUG,
                materialized_at=self.materialized_at,
                subject=gene, predicate="gene_drug_interaction", object=drug, disease=[],
                **self._base_non_evidence(),
                intervention_expression_raw=drug["label"],
                intervention_components=[{"concept_id": drug_id, "name": drug["label"],
                                          "node_id": f"Drug:{drug_id}",
                                          "component_role": "UNKNOWN"}],
                intervention_structure="SINGLE_AGENT",
                regimen_semantics_status=NOT_APPLICABLE,
                regimen_id=None, regimen_limitations=[],
                biomarkers=[gene], evidence_scope=row.get("source_db"), diagnostic_scope=None,
                graph_path=[gene["id"], drug["id"]], node_ids=[gene["id"], drug["id"]],
                edge_ids=[edge_id], evidence_record_ids=[], document_identifiers=[],
                source_properties={"interaction": row},
                source_path_ids=[f"{RULE_GENE_DRUG}#{edge_id}"],
                v2_candidate_ids=[], known_limitations=[],
            ))
        return out

    def _companion_diagnostic_candidates(self) -> list[GraphCandidateAssertionV3]:
        out = []
        for edge_id, row in self.graph.edge_rows("edge_diagnoses_gene.csv"):
            device_id = _clean(row.get("source_device_id"))
            gene_id = _clean(row.get("target_gene_entrez_id"))
            device = self.devices.get(device_id)
            if not device:
                self.excluded.append({"path_id": edge_id,
                                      "reason": "MISSING_COMPANION_DIAGNOSTIC_NODE"})
                continue
            gene = _typed(gene_id, "Gene")
            gene["label"] = self.genes.get(gene_id, {}).get("hugo_symbol") or gene_id
            diagnostic = _typed(device_id, "CompanionDiagnostic")
            diagnostic["label"] = device.get("device_name") or device_id
            edge_ids = [e for e, _ in self.cdx_by_device.get(device_id, [])] + [edge_id]
            out.append(GraphCandidateAssertionV3.from_parts(
                materialization_rule_id=RULE_COMPANION_DIAGNOSTIC,
                materialized_at=self.materialized_at,
                subject=gene, predicate="has_companion_diagnostic", object=diagnostic,
                disease=[], **self._base_non_evidence(),
                intervention_expression_raw=None, intervention_components=[],
                intervention_structure=STRUCTURE_UNKNOWN,
                regimen_semantics_status=NOT_APPLICABLE, regimen_id=None,
                regimen_limitations=[],
                biomarkers=[gene], evidence_scope=None,
                diagnostic_scope="CompanionDiagnostic",
                graph_path=[gene["id"], diagnostic["id"]],
                node_ids=[gene["id"], diagnostic["id"]], edge_ids=edge_ids,
                evidence_record_ids=[], document_identifiers=[],
                source_properties={"diagnostic": device},
                source_path_ids=[f"{RULE_COMPANION_DIAGNOSTIC}#{edge_id}"],
                v2_candidate_ids=[], known_limitations=[],
            ))
        return out

    def _trial_candidates(self) -> list[GraphCandidateAssertionV3]:
        out = []
        for edge_id, row in self.graph.edge_rows("edges_trial_drug.csv"):
            nct = _clean(row.get("nct_id"))
            if not nct:
                self.excluded.append({"path_id": edge_id, "reason": "MISSING_NCT"})
                continue
            trial = _typed(nct, "ClinicalTrial")
            name = row.get("drug_name_normalized") or row.get("drug_name_raw")
            drug = _typed(name, "Drug")
            out.append(GraphCandidateAssertionV3.from_parts(
                materialization_rule_id=RULE_TRIAL_DRUG,
                materialized_at=self.materialized_at,
                subject=trial, predicate="trial_association", object=drug, disease=[],
                **self._base_non_evidence(),
                intervention_expression_raw=drug["label"],
                intervention_components=[{"concept_id": None, "name": drug["label"],
                                          "node_id": drug["id"], "component_role": "UNKNOWN"}],
                intervention_structure="SINGLE_AGENT",
                regimen_semantics_status=NOT_APPLICABLE, regimen_id=None,
                regimen_limitations=[],
                biomarkers=[], evidence_scope="clinical_trial", diagnostic_scope=None,
                graph_path=[trial["id"], drug["id"]], node_ids=[trial["id"], drug["id"]],
                edge_ids=[edge_id], evidence_record_ids=[],
                document_identifiers=[{"nct": nct, "scope": "clinical_trial"}],
                source_properties={"trial_drug": row},
                source_path_ids=[f"{RULE_TRIAL_DRUG}#{edge_id}"],
                v2_candidate_ids=[], known_limitations=[],
            ))
        for edge_id, row in self.graph.edge_rows("edges_trial_gene.csv"):
            nct = _clean(row.get("nct_id"))
            if not nct:
                self.excluded.append({"path_id": edge_id, "reason": "MISSING_NCT"})
                continue
            trial = _typed(nct, "ClinicalTrial")
            gene = _typed(row.get("gene_symbol"), "Gene")
            out.append(GraphCandidateAssertionV3.from_parts(
                materialization_rule_id=RULE_TRIAL_GENE,
                materialized_at=self.materialized_at,
                subject=trial, predicate="trial_association", object=gene, disease=[],
                **self._base_non_evidence(),
                intervention_expression_raw=None, intervention_components=[],
                intervention_structure=STRUCTURE_UNKNOWN,
                regimen_semantics_status=NOT_APPLICABLE, regimen_id=None,
                regimen_limitations=[],
                biomarkers=[gene], evidence_scope="clinical_trial", diagnostic_scope=None,
                graph_path=[trial["id"], gene["id"]], node_ids=[trial["id"], gene["id"]],
                edge_ids=[edge_id], evidence_record_ids=[],
                document_identifiers=[{"nct": nct, "scope": "clinical_trial"}],
                source_properties={"trial_gene": row},
                source_path_ids=[f"{RULE_TRIAL_GENE}#{edge_id}"],
                v2_candidate_ids=[], known_limitations=[],
            ))
        return out

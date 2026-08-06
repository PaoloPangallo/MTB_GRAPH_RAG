"""Ricostruzione **indipendente** dei path eleggibili dal Knowledge Graph.

Sorgente: l'export CSV congelato dichiarato in ``manifest.json`` come
``regenerable_from``. Neo4j non è la sorgente della materializzazione e non
viene interrogata (cfr. ``docs/evaluation/01_evaluation_protocol.md``).

**Perché non si riesegue il materializzatore.** Il modulo originale
(``benchmarks/mtb_evidence/document_grounded_claims/kg.py`` al commit
``3694979``) è recuperabile da git. Rieseguirlo e confrontare l'output con
``candidates.jsonl`` misurerebbe soltanto il determinismo dello stesso codice:
precision e recall verrebbero 1.0 per costruzione, qualunque sia la correttezza
delle regole. Questo modulo riderivava quindi i path leggendo direttamente le
tabelle CSV, seguendo le sei regole dichiarate in
``materialization_rules.json``, e ricostruisce in modo indipendente i valori
attesi di ogni campo.

**Cosa resta condiviso, e perché è lecito.** Due funzioni sono *identità*, non
regole semantiche: la derivazione di ``edge_id`` da (file, riga, indice) e
quella di ``candidate_id``/``payload_hash`` dal payload. Sono documentate in
``schema.json`` come ``deterministic_sha256_prefix``. Riprodurle serve a
verificare il lineage; non può mascherare un errore di contenuto, perché un
campo sbagliato cambia comunque il digest.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Tabelle nodo: file -> (tipo di nodo, colonna chiave primaria).
NODE_KEYS: dict[str, tuple[str, str]] = {
    "node_evidence.csv": ("Evidence", "evidence_id"),
    "node_gene.csv": ("Gene", "entrez_id"),
    "node_variant.csv": ("Variant", "variant_id"),
    "node_molecular_profile.csv": ("MolecularProfile", "molecular_profile_id"),
    "node_drug.csv": ("Drug", "concept_id"),
    "node_companion_diagnostic.csv": ("CompanionDiagnostic", "device_id"),
    "nodes_clinical_trials.csv": ("ClinicalTrial", "nct_id"),
    "civic_diseases.csv": ("Disease", "disease_id"),
    "civic_publications.csv": ("Publication", "pmid"),
}

EDGE_FILES = (
    "edge_has_evidence.csv",
    "edge_has_variant.csv",
    "edge_in_molecular_profile.csv",
    "edge_targets_drug.csv",
    "edge_interacts_with.csv",
    "edge_has_companion_diagnostic.csv",
    "edge_diagnoses_gene.csv",
    "edges_trial_drug.csv",
    "edges_trial_gene.csv",
    "civic_evidence_disease_links.csv",
    "civic_evidence_publication_links.csv",
)

#: Le sei regole dichiarate in ``materialization_rules.json``.
RULE_EVIDENCE_STATEMENT = "gca/2.0/evidence-statement"
RULE_EVIDENCE_TO_DRUG = "gca/2.0/evidence-to-drug"
RULE_GENE_DRUG = "gca/2.0/gene-drug-interaction"
RULE_COMPANION_DIAGNOSTIC = "gca/2.0/companion-diagnostic"
RULE_TRIAL_DRUG = "gca/2.0/trial-drug"
RULE_TRIAL_GENE = "gca/2.0/trial-gene"

NULL_TOKENS = {"", "nan", "none", "null"}


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def edge_identity(filename: str, row: dict[str, str], index: int) -> str:
    """Identità deterministica di un arco. Funzione di identità, non regola."""
    return f"edge:{Path(filename).stem}:{_sha({'row': row, 'index': index})[:16]}"


def payload_identity(payload: dict[str, Any]) -> tuple[str, str]:
    """``(candidate_id, payload_hash)`` dal payload. Funzione di identità."""
    digest = _sha(payload)
    return f"GCA-{digest[:24]}", digest


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _typed(value: Any, prefix: str) -> dict[str, Any]:
    """Nodo tipizzato nella forma emessa dalla materializzazione."""
    text = _clean(value)
    return {
        "id": f"{prefix}:{text}" if text else f"{prefix}:missing",
        "type": prefix,
        "label": text or None,
        "canonical_id": None,
    }


@dataclass
class EligiblePath:
    """Un path del grafo eleggibile alla materializzazione, con i campi attesi.

    ``expected`` contiene i valori che una materializzazione fedele deve
    produrre. ``diagnostics`` contiene osservazioni sul grafo che *non* sono
    attese ma servono a interpretare gli scostamenti (per esempio l'insieme
    completo delle varianti di un profilo, quando la materializzazione ne
    conserva una sola).
    """

    path_id: str
    rule_id: str
    source_table: str
    source_row_index: int
    expected: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def identity(self) -> tuple:
        """Identità del path: regola + nodi + archi (ordinati)."""
        return (
            self.rule_id,
            self.expected.get("predicate"),
            tuple(self.expected.get("node_ids") or []),
            tuple(sorted(self.expected.get("edge_ids") or [])),
        )


@dataclass
class ExcludedPath:
    path_id: str
    rule_id: str
    reason: str
    node_ids: list[str]
    edge_ids: list[str]


class FrozenKnowledgeGraph:
    """Lettore read-only dell'export CSV congelato."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.tables: dict[str, list[dict[str, str]]] = {}
        self.columns: dict[str, list[str]] = {}
        for path in sorted(self.root.glob("*.csv")):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.columns[path.name] = list(reader.fieldnames or [])
                self.tables[path.name] = list(reader)

    # ---------------------------------------------------------------- indici

    def fingerprint(self) -> dict[str, Any]:
        """Impronta della sorgente, per la riproducibilità."""
        files = {}
        for path in sorted(self.root.glob("*")):
            if path.is_file():
                files[path.name] = {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
        return {
            "source_root": str(self.root),
            "files": files,
            "corpus_fingerprint": _sha(files),
        }

    def node_index(self, filename: str) -> dict[str, dict[str, str]]:
        spec = NODE_KEYS.get(filename)
        if not spec:
            return {}
        _, key = spec
        return {_clean(row.get(key)): row for row in self.tables.get(filename, []) if _clean(row.get(key))}

    def edge_rows(self, filename: str) -> list[tuple[str, dict[str, str]]]:
        """Archi con identità deterministica, nell'ordine del file (1-based)."""
        return [
            (edge_identity(filename, row, index), row)
            for index, row in enumerate(self.tables.get(filename, []), start=1)
        ]

    def inventory(self) -> dict[str, Any]:
        node_counts = {n: len(r) for n, r in self.tables.items() if n in NODE_KEYS}
        edge_counts = {n: len(r) for n, r in self.tables.items() if n in EDGE_FILES}
        return {
            "source_root": str(self.root),
            "node_counts": node_counts,
            "edge_counts": edge_counts,
            "total_nodes": sum(node_counts.values()),
            "total_edges": sum(edge_counts.values()),
            "evidence_records": len(self.tables.get("node_evidence.csv", [])),
        }


class EligiblePathBuilder:
    """Enumera i path eleggibili applicando le sei regole dichiarate."""

    def __init__(self, graph: FrozenKnowledgeGraph):
        self.graph = graph
        self.evidence = graph.node_index("node_evidence.csv")
        self.profiles = graph.node_index("node_molecular_profile.csv")
        self.variants = graph.node_index("node_variant.csv")
        self.genes = graph.node_index("node_gene.csv")
        self.drugs = graph.node_index("node_drug.csv")
        self.diseases = graph.node_index("civic_diseases.csv")
        self.devices = graph.node_index("node_companion_diagnostic.csv")

        self.pub_links: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for edge_id, row in graph.edge_rows("civic_evidence_publication_links.csv"):
            self.pub_links[_clean(row.get("evidence_id"))].append((edge_id, row))

        self.disease_links: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for edge_id, row in graph.edge_rows("civic_evidence_disease_links.csv"):
            self.disease_links[_clean(row.get("evidence_id"))].append((edge_id, row))

        self.profile_variants: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_in_molecular_profile.csv"):
            self.profile_variants[_clean(row.get("target_molecular_profile_id"))].append((edge_id, row))

        self.variant_genes: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_has_variant.csv"):
            self.variant_genes[_clean(row.get("target_variant_id"))].append((edge_id, row))

        self.drug_edges_by_evidence: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_targets_drug.csv"):
            self.drug_edges_by_evidence[_clean(row.get("source_evidence_id"))].append((edge_id, row))

        self.cdx_by_device: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for edge_id, row in graph.edge_rows("edge_has_companion_diagnostic.csv"):
            self.cdx_by_device[_clean(row.get("target_device_id"))].append((edge_id, row))

        self.excluded: list[ExcludedPath] = []

    # ------------------------------------------------------------- contesto

    def _document_identifiers(self, evidence_id: str, erow: dict) -> list[dict]:
        identifiers: list[dict] = []
        pmid = _clean(erow.get("citation_id"))
        if pmid and pmid.lower() not in NULL_TOKENS:
            identifiers.append({"pmid": pmid, "scope": "evidence_record"})
        for _, row in self.pub_links.get(evidence_id, []):
            pmid = _clean(row.get("pmid"))
            entry = {"pmid": pmid, "scope": "linked_publication"}
            if pmid and entry not in identifiers:
                identifiers.append(entry)
        return identifiers

    def _disease_context(self, evidence_id: str, erow: dict) -> list[dict]:
        values: list[dict] = []
        raw = _clean(erow.get("disease"))
        doid = _clean(erow.get("doid"))
        if raw:
            values.append({
                "id": f"disease:label:{raw}",
                "label": raw,
                "canonical_id": f"DOID:{doid}" if doid and doid != "nan" else None,
            })
        for _, link in self.disease_links.get(evidence_id, []):
            did = _clean(link.get("disease_id"))
            drow = self.diseases.get(did, {})
            value = {
                "id": f"Disease:{did}",
                "label": drow.get("disease") or did,
                "canonical_id": f"DOID:{drow.get('doid')}" if drow.get("doid") else None,
            }
            if value not in values:
                values.append(value)
        return values

    def _exclude(self, path_id, rule_id, reason, node_ids=None, edge_ids=None) -> None:
        self.excluded.append(ExcludedPath(path_id, rule_id, reason, node_ids or [], edge_ids or []))

    # -------------------------------------------------------------- le regole

    def build(self) -> list[EligiblePath]:
        paths: list[EligiblePath] = []
        paths.extend(self._evidence_paths())
        paths.extend(self._gene_drug_paths())
        paths.extend(self._companion_diagnostic_paths())
        paths.extend(self._trial_paths())
        return paths

    def _evidence_paths(self) -> list[EligiblePath]:
        """Regole ``evidence-statement`` e ``evidence-to-drug``.

        L'unità eleggibile è la riga di ``edge_has_evidence.csv``: un profilo
        molecolare collegato a un record Evidence. Da essa discendono una
        candidate per lo statement (se non vuoto) e una per ogni farmaco
        bersaglio del record Evidence.
        """
        out: list[EligiblePath] = []
        for index, (edge_profile_id, profile_edge) in enumerate(
            self.graph.edge_rows("edge_has_evidence.csv"), start=1
        ):
            profile_id = _clean(profile_edge.get("source_molecular_profile_id"))
            evidence_id = _clean(profile_edge.get("target_evidence_id"))
            erow = self.evidence.get(evidence_id)
            profile = self.profiles.get(profile_id)
            if not erow or not profile:
                self._exclude(
                    edge_profile_id, RULE_EVIDENCE_STATEMENT, "MISSING_EVIDENCE_OR_PROFILE",
                    [f"MolecularProfile:{profile_id}", f"Evidence:{evidence_id}"], [edge_profile_id],
                )
                continue

            pvars = self.profile_variants.get(profile_id, [])
            variant_id = _clean(pvars[0][1].get("source_variant_id")) if pvars else ""
            vrow = self.variants.get(variant_id, {})
            gene_links = self.variant_genes.get(variant_id, [])
            gene_id = _clean(gene_links[0][1].get("source_entrez_id")) if gene_links else ""
            grow = self.genes.get(gene_id, {})

            subject = _typed(variant_id or profile_id, "Variant" if variant_id else "MolecularProfile")
            subject["label"] = vrow.get("variant_name") or profile.get("name") or subject["label"]

            biomarkers: list[dict] = []
            if grow:
                gene_node = _typed(gene_id, "Gene")
                gene_node["label"] = grow.get("hugo_symbol")
                biomarkers.append(gene_node)
            if vrow:
                variant_node = _typed(variant_id, "Variant")
                variant_node["label"] = vrow.get("variant_name")
                biomarkers.append(variant_node)

            disease = self._disease_context(evidence_id, erow)
            documents = self._document_identifiers(evidence_id, erow)
            context_nodes = [subject["id"], f"MolecularProfile:{profile_id}", f"Evidence:{evidence_id}"]
            context_edges = [e for e, _ in pvars] + [e for e, _ in gene_links] + [edge_profile_id]

            # Osservazioni sul grafo che non sono valori attesi ma spiegano le perdite.
            all_variants = sorted({_clean(r.get("source_variant_id")) for _, r in pvars} - {""})
            all_genes_of_first = sorted({_clean(r.get("source_entrez_id")) for _, r in gene_links} - {""})
            diagnostics = {
                "profile_variant_count": len(all_variants),
                "profile_variant_ids": all_variants,
                "selected_variant_id": variant_id,
                "dropped_variant_ids": [v for v in all_variants if v != variant_id],
                "first_variant_gene_count": len(all_genes_of_first),
                "selected_gene_id": gene_id,
                "dropped_gene_ids": [g for g in all_genes_of_first if g != gene_id],
                "evidence_direction": _clean(erow.get("evidence_direction")) or None,
                "evidence_significance": _clean(erow.get("significance")) or None,
                "evidence_level": _clean(erow.get("evidence_level")) or None,
                "evidence_type": _clean(erow.get("evidence_type")) or None,
            }

            statement = _clean(erow.get("evidence_statement"))
            if statement:
                out.append(EligiblePath(
                    path_id=f"{RULE_EVIDENCE_STATEMENT}#{edge_profile_id}",
                    rule_id=RULE_EVIDENCE_STATEMENT,
                    source_table="edge_has_evidence.csv",
                    source_row_index=index,
                    expected={
                        "subject": subject,
                        "predicate": "has_evidence_statement",
                        "object": _typed(evidence_id, "Evidence"),
                        "disease": disease,
                        "biomarkers": biomarkers,
                        "interventions": [],
                        "regimen": [],
                        "direction": erow.get("evidence_direction"),
                        "evidence_scope": erow.get("evidence_type"),
                        "diagnostic_scope": None,
                        "graph_path": context_nodes,
                        "node_ids": context_nodes,
                        "edge_ids": context_edges,
                        "evidence_record_ids": [f"evidence:{evidence_id}"],
                        "document_identifiers": documents,
                        "source_properties": {"evidence": erow, "profile": profile},
                    },
                    diagnostics=diagnostics,
                ))
            else:
                self._exclude(
                    f"evidence-statement:{evidence_id}", RULE_EVIDENCE_STATEMENT,
                    "EMPTY_EVIDENCE_STATEMENT", context_nodes, context_edges,
                )

            for edge_drug_id, drug_edge in self.drug_edges_by_evidence.get(evidence_id, []):
                drug_id = _clean(drug_edge.get("target_drug_concept_id"))
                drow = self.drugs.get(drug_id)
                if not drow:
                    self._exclude(
                        edge_drug_id, RULE_EVIDENCE_TO_DRUG, "MISSING_DRUG_NODE",
                        context_nodes + [f"Drug:{drug_id}"], [edge_drug_id],
                    )
                    continue
                significance = _clean(drug_edge.get("significance")) or _clean(erow.get("significance"))
                low = significance.lower()
                if "resistance" in low:
                    predicate = "associated_with_resistance_to"
                elif "sensitivity" in low or "response" in low:
                    predicate = "associated_with_sensitivity_to"
                else:
                    predicate = "evidence_association"
                drug = _typed(drug_id, "Drug")
                drug["label"] = drow.get("drug_name") or drug_id
                out.append(EligiblePath(
                    path_id=f"{RULE_EVIDENCE_TO_DRUG}#{edge_profile_id}#{edge_drug_id}",
                    rule_id=RULE_EVIDENCE_TO_DRUG,
                    source_table="edge_targets_drug.csv",
                    source_row_index=index,
                    expected={
                        "subject": subject,
                        "predicate": predicate,
                        "object": drug,
                        "disease": disease,
                        "biomarkers": biomarkers,
                        "interventions": [drug],
                        "regimen": [],
                        "direction": significance or erow.get("evidence_direction") or None,
                        "evidence_scope": erow.get("evidence_type"),
                        "diagnostic_scope": None,
                        "graph_path": context_nodes + [drug["id"]],
                        "node_ids": context_nodes + [drug["id"]],
                        "edge_ids": context_edges + [edge_drug_id],
                        "evidence_record_ids": [f"evidence:{evidence_id}"],
                        "document_identifiers": documents,
                        "source_properties": {
                            "evidence": erow, "target_edge": drug_edge,
                            "profile": profile, "drug": drow,
                        },
                    },
                    diagnostics={
                        **diagnostics,
                        "edge_significance": _clean(drug_edge.get("significance")) or None,
                        "edge_evidence_direction": _clean(drug_edge.get("evidence_direction")) or None,
                    },
                ))
        return out

    def _gene_drug_paths(self) -> list[EligiblePath]:
        out: list[EligiblePath] = []
        for index, (edge_id, row) in enumerate(self.graph.edge_rows("edge_interacts_with.csv"), start=1):
            gene_id = _clean(row.get("source_gene_entrez_id"))
            drug_id = _clean(row.get("target_drug_concept_id"))
            if not (gene_id and drug_id):
                self._exclude(edge_id, RULE_GENE_DRUG, "MISSING_INTERACTION_ENDPOINT", [], [edge_id])
                continue
            gene = _typed(gene_id, "Gene")
            gene["label"] = self.genes.get(gene_id, {}).get("hugo_symbol") or gene_id
            drug = _typed(drug_id, "Drug")
            drug["label"] = self.drugs.get(drug_id, {}).get("drug_name") or drug_id
            out.append(EligiblePath(
                path_id=f"{RULE_GENE_DRUG}#{edge_id}",
                rule_id=RULE_GENE_DRUG,
                source_table="edge_interacts_with.csv",
                source_row_index=index,
                expected={
                    "subject": gene,
                    "predicate": "gene_drug_interaction",
                    "object": drug,
                    "disease": [],
                    "biomarkers": [gene],
                    "interventions": [drug],
                    "regimen": [],
                    "direction": None,
                    "evidence_scope": row.get("source_db"),
                    "diagnostic_scope": None,
                    "graph_path": [gene["id"], drug["id"]],
                    "node_ids": [gene["id"], drug["id"]],
                    "edge_ids": [edge_id],
                    "evidence_record_ids": [],
                    "document_identifiers": [],
                    "source_properties": {"interaction": row},
                },
                diagnostics={"source_db": _clean(row.get("source_db")) or None},
            ))
        return out

    def _companion_diagnostic_paths(self) -> list[EligiblePath]:
        out: list[EligiblePath] = []
        for index, (edge_id, row) in enumerate(self.graph.edge_rows("edge_diagnoses_gene.csv"), start=1):
            device_id = _clean(row.get("source_device_id"))
            gene_id = _clean(row.get("target_gene_entrez_id"))
            device = self.devices.get(device_id)
            if not device:
                self._exclude(
                    edge_id, RULE_COMPANION_DIAGNOSTIC, "MISSING_COMPANION_DIAGNOSTIC_NODE",
                    [f"CompanionDiagnostic:{device_id}"], [edge_id],
                )
                continue
            gene = _typed(gene_id, "Gene")
            gene["label"] = self.genes.get(gene_id, {}).get("hugo_symbol") or gene_id
            diagnostic = _typed(device_id, "CompanionDiagnostic")
            diagnostic["label"] = device.get("device_name") or device_id
            edge_ids = [e for e, _ in self.cdx_by_device.get(device_id, [])] + [edge_id]
            out.append(EligiblePath(
                path_id=f"{RULE_COMPANION_DIAGNOSTIC}#{edge_id}",
                rule_id=RULE_COMPANION_DIAGNOSTIC,
                source_table="edge_diagnoses_gene.csv",
                source_row_index=index,
                expected={
                    "subject": gene,
                    "predicate": "has_companion_diagnostic",
                    "object": diagnostic,
                    "disease": [],
                    "biomarkers": [gene],
                    "interventions": [],
                    "regimen": [],
                    "direction": None,
                    "evidence_scope": None,
                    "diagnostic_scope": "CompanionDiagnostic",
                    "graph_path": [gene["id"], diagnostic["id"]],
                    "node_ids": [gene["id"], diagnostic["id"]],
                    "edge_ids": edge_ids,
                    "evidence_record_ids": [],
                    "document_identifiers": [],
                    "source_properties": {"diagnostic": device},
                },
                diagnostics={"device_drug": device.get("drug"), "device_gene": device.get("gene")},
            ))
        return out

    def _trial_paths(self) -> list[EligiblePath]:
        out: list[EligiblePath] = []
        for index, (edge_id, row) in enumerate(self.graph.edge_rows("edges_trial_drug.csv"), start=1):
            nct = _clean(row.get("nct_id"))
            if not nct:
                self._exclude(edge_id, RULE_TRIAL_DRUG, "MISSING_NCT", [], [edge_id])
                continue
            trial = _typed(nct, "ClinicalTrial")
            drug = _typed(row.get("drug_name_normalized") or row.get("drug_name_raw"), "Drug")
            out.append(EligiblePath(
                path_id=f"{RULE_TRIAL_DRUG}#{edge_id}",
                rule_id=RULE_TRIAL_DRUG,
                source_table="edges_trial_drug.csv",
                source_row_index=index,
                expected={
                    "subject": trial,
                    "predicate": "trial_association",
                    "object": drug,
                    "disease": [],
                    "biomarkers": [],
                    "interventions": [drug],
                    "regimen": [],
                    "direction": None,
                    "evidence_scope": "clinical_trial",
                    "diagnostic_scope": None,
                    "graph_path": [trial["id"], drug["id"]],
                    "node_ids": [trial["id"], drug["id"]],
                    "edge_ids": [edge_id],
                    "evidence_record_ids": [],
                    "document_identifiers": [{"nct": nct, "scope": "clinical_trial"}],
                    "source_properties": {"trial_drug": row},
                },
                diagnostics={"drug_name_raw": row.get("drug_name_raw")},
            ))
        for index, (edge_id, row) in enumerate(self.graph.edge_rows("edges_trial_gene.csv"), start=1):
            nct = _clean(row.get("nct_id"))
            if not nct:
                self._exclude(edge_id, RULE_TRIAL_GENE, "MISSING_NCT", [], [edge_id])
                continue
            trial = _typed(nct, "ClinicalTrial")
            gene = _typed(row.get("gene_symbol"), "Gene")
            out.append(EligiblePath(
                path_id=f"{RULE_TRIAL_GENE}#{edge_id}",
                rule_id=RULE_TRIAL_GENE,
                source_table="edges_trial_gene.csv",
                source_row_index=index,
                expected={
                    "subject": trial,
                    "predicate": "trial_association",
                    "object": gene,
                    "disease": [],
                    "biomarkers": [gene],
                    "interventions": [],
                    "regimen": [],
                    "direction": None,
                    "evidence_scope": "clinical_trial",
                    "diagnostic_scope": None,
                    "graph_path": [trial["id"], gene["id"]],
                    "node_ids": [trial["id"], gene["id"]],
                    "edge_ids": [edge_id],
                    "evidence_record_ids": [],
                    "document_identifiers": [{"nct": nct, "scope": "clinical_trial"}],
                    "source_properties": {"trial_gene": row},
                },
                diagnostics={"source": row.get("source")},
            ))
        return out


def expected_payload(path: EligiblePath, group_id: Any = None) -> dict[str, Any]:
    """Payload atteso, nella forma su cui è calcolato ``payload_hash``."""
    exp = path.expected
    return {
        "subject": exp["subject"],
        "predicate": exp["predicate"],
        "object": exp["object"],
        "disease": exp["disease"],
        "biomarkers": exp["biomarkers"],
        "interventions": exp["interventions"],
        "regimen": exp["regimen"],
        "direction": exp["direction"],
        "evidence_scope": exp["evidence_scope"],
        "diagnostic_scope": exp["diagnostic_scope"],
        "graph_path": exp["graph_path"],
        "node_ids": exp["node_ids"],
        "edge_ids": exp["edge_ids"],
        "evidence_record_ids": exp["evidence_record_ids"],
        "document_identifiers": exp["document_identifiers"],
        "source_properties": exp["source_properties"],
        "materialization_rule_id": path.rule_id,
        "group_id": group_id,
    }

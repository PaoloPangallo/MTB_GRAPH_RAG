"""Report di audit, proposte di emendamento e pacchetto per il secondo revisore.

Nessuna funzione di questo modulo scrive sul gold. Le divergenze diventano righe di
`proposed_gold_amendments.jsonl`, tutte con `requires_human_review: true`.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .gold import GoldCase
from .queries.base import CaseOutcome

KEEP = "KEEP"
AMEND = "AMEND"
REPLACE = "REPLACE"
REJECT = "REJECT"

# Il pacchetto per il secondo revisore non deve contenere nulla che suggerisca la
# risposta: ne' la decisione dell'audit, ne' output del modello o del planner.
FORBIDDEN_REVIEW_PATTERNS: tuple[str, ...] = (
    "risposta corretta",
    "correct answer",
    "accetta questa",
    "accept this claim",
    "raccomandiamo",
    "we recommend",
    "graphrag",
    "planner",
    "prediction",
    "predizione",
    "decisione proposta",
    "proposed decision",
    "keep/amend",
    "freeze_ready",
)


def decide(case: GoldCase, comparison: Mapping[str, Any], outcome: CaseOutcome) -> dict[str, Any]:
    """Decisione proposta per il caso, con la motivazione che la sostiene."""
    blockers = list(comparison.get("freeze_blockers", []))
    matched = comparison.get("structurally_matching_claims", [])
    partial = comparison.get("partially_matching_claims", [])
    unmatched = comparison.get("unmatched_claims", [])

    if outcome.blockers:
        return {
            "decision": REJECT,
            "rationale": (
                "La premessa del caso e' contraddetta dallo snapshot: "
                + "; ".join(outcome.blockers)
            ),
        }
    if comparison.get("freeze_ready"):
        return {
            "decision": KEEP,
            "rationale": "Nessun freeze blocker: gold e grafo concordano su tutte le dimensioni.",
        }
    if not matched and not partial and unmatched:
        return {
            "decision": REPLACE,
            "rationale": (
                "Nessuna claim trova un record corrispondente nello snapshot: il caso "
                "andrebbe riscritto su evidenze effettivamente presenti, oppure "
                "riqualificato come caso di copertura mancante."
            ),
        }
    return {
        "decision": AMEND,
        "rationale": (
            f"{len(matched)} claim pienamente corrispondenti, {len(partial)} parziali, "
            f"{len(unmatched)} senza riscontro; {len(blockers)} freeze blocker da risolvere "
            "prima del congelamento."
        ),
    }


def build_amendments(
    case: GoldCase, comparison: Mapping[str, Any], outcome: CaseOutcome
) -> list[dict[str, Any]]:
    """Proposte di emendamento, mai applicate automaticamente."""
    proposals: list[dict[str, Any]] = []
    source_ids = [source.source_record_id for source in case.sources]
    record_ids = [claim.record_id for claim in outcome.graph_claims if claim.record_id]

    def add(field: str, current: Any, proposed: Any, reason: str, confidence: str) -> None:
        proposals.append(
            {
                "case_id": case.case_id,
                "field": field,
                "current_value": current,
                "proposed_value": proposed,
                "reason": reason,
                "supporting_graph_record_ids": record_ids[:20],
                "supporting_source_ids": source_ids,
                "confidence": confidence,
                "requires_human_review": True,
            }
        )

    missing_pmids = comparison.get("missing_pmids", [])
    if missing_pmids:
        add(
            "expected_pmids",
            list(case.expected_pmids),
            sorted(set(comparison.get("expected_pmids", [])) - set(missing_pmids)),
            (
                f"I PMID {missing_pmids} non esistono come nodo Publication nello snapshot. "
                "Il gold puo' conservarli come fonti documentali esterne, ma non possono "
                "essere richiesti a una pipeline snapshot-defined."
            ),
            "high",
        )

    missing_ncts = comparison.get("missing_nct_ids", [])
    if missing_ncts:
        add(
            "expected_nct_ids",
            list(case.expected_nct_ids),
            sorted(set(comparison.get("expected_nct_ids", [])) - set(missing_ncts)),
            (
                f"Gli NCT {missing_ncts} non esistono come nodo ClinicalTrial nello snapshot. "
                "Stessa distinzione fra fonte documentale e fonte recuperabile."
            ),
            "high",
        )

    missing_therapies = comparison.get("missing_therapies", [])
    if missing_therapies:
        add(
            "expected_therapies",
            list(case.expected_therapies),
            sorted(set(comparison.get("expected_therapies", [])) - set(missing_therapies)),
            (
                f"Le terapie {missing_therapies} non sono raggiungibili dal traversal per "
                "questo profilo, anche quando il nodo Drug esiste: manca il collegamento "
                "evidenza -> farmaco nel contesto del caso."
            ),
            "medium",
        )

    for conflict in comparison.get("conflicts", []):
        add(
            f"claims[{conflict['claim_id']}].{conflict['dimension']}",
            conflict.get("gold_value"),
            conflict.get("graph_value"),
            (
                f"Divergenza sulla dimensione {conflict['dimension']}: {conflict.get('detail', '')}. "
                "Va deciso da un revisore se il gold descrive una popolazione piu' stretta "
                "di quella rappresentata nel grafo, o se il grafo e' impreciso."
            ),
            "medium",
        )

    for warning in outcome.warnings:
        if "non sono modellati dallo schema" in warning or "non e' modellata" in warning:
            add(
                "required_context",
                case.required_context,
                case.required_context,
                (
                    f"Nessuna modifica di valore proposta. Limite di schema da registrare: {warning}. "
                    "Il qualificatore resta valido per l'annotazione umana ma non e' verificabile "
                    "automaticamente sullo snapshot."
                ),
                "informational",
            )

    return proposals


def _bullet_list(items: Iterable[Any], empty: str = "nessuno") -> str:
    values = [str(item) for item in items]
    if not values:
        return f"- _{empty}_"
    return "\n".join(f"- `{value}`" for value in values)


def build_case_discrepancies_md(
    case: GoldCase, comparison: Mapping[str, Any], outcome: CaseOutcome, decision: Mapping[str, Any]
) -> str:
    lines = [
        f"# Discrepanze - {case.case_id}",
        "",
        f"**Categoria:** {case.category}",
        f"**Stato annotazione:** {case.annotation_status}",
        "",
        "## Terapie",
        "",
        "**Attese**",
        _bullet_list(comparison["expected_therapies"]),
        "",
        "**Trovate nel grafo**",
        _bullet_list(comparison["found_therapies"]),
        "",
        "**Mancanti**",
        _bullet_list(comparison["missing_therapies"]),
        "",
        "**In piu'**",
        _bullet_list(comparison["extra_therapies"]),
        "",
        "## PMID",
        "",
        "**Mancanti**",
        _bullet_list(comparison["missing_pmids"]),
        "",
        "**Trovati**",
        _bullet_list(comparison["found_pmids"]),
        "",
        "## NCT",
        "",
        "**Mancanti**",
        _bullet_list(comparison["missing_nct_ids"]),
        "",
        "**Trovati**",
        _bullet_list(comparison["found_nct_ids"]),
        "",
        "## Claim",
        "",
        f"- pienamente corrispondenti: {len(comparison['structurally_matching_claims'])}",
        f"- parzialmente corrispondenti: {len(comparison['partially_matching_claims'])}",
        f"- senza riscontro: {len(comparison['unmatched_claims'])}",
        "",
    ]

    if comparison["conflicts"]:
        lines += ["## Conflitti", ""]
        for conflict in comparison["conflicts"]:
            lines.append(
                f"- **{conflict['claim_id']}** / `{conflict['dimension']}`: "
                f"gold `{conflict['gold_value']}` vs grafo `{conflict['graph_value']}` "
                f"({conflict['detail']})"
            )
        lines.append("")

    lines += [
        "## Qualificatori non modellati dallo schema",
        "",
        _bullet_list(comparison["not_modelled_by_schema"]),
        "",
        "## Avvertenze",
        "",
        _bullet_list(outcome.warnings, empty="nessuna"),
        "",
        "## Freeze blockers",
        "",
        _bullet_list(comparison["freeze_blockers"], empty="nessuno"),
        "",
        f"**Freeze ready:** {'si' if comparison['freeze_ready'] else 'no'}",
        "",
        f"**Decisione proposta:** {decision['decision']}",
        "",
        decision["rationale"],
        "",
    ]
    return "\n".join(lines)


def build_audit_report_md(
    entries: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> str:
    fingerprint = manifest.get("snapshot_fingerprint", {}).get("value", "unknown")
    lines = [
        "# Audit del gold pilota MTB-Evidence contro lo snapshot Neo4j",
        "",
        f"- **Timestamp (UTC):** {manifest.get('audit_timestamp_utc')}",
        f"- **Commit:** `{manifest.get('commit_sha')}`",
        f"- **Neo4j:** {manifest.get('neo4j_version')} {manifest.get('neo4j_edition')} "
        f"su `{manifest.get('neo4j_uri')}`, database `{manifest.get('database_name')}`",
        f"- **Fingerprint snapshot:** `{fingerprint}`",
        f"- **Nodi / relazioni:** {manifest.get('total_nodes')} / "
        f"{manifest.get('total_relationships')}",
        "",
        "Questo documento e' un audit del grafo. Non modifica il gold, non usa output "
        "del modello come ground truth e non formula raccomandazioni cliniche: constata "
        "quali record esistono nello snapshot e come si rapportano all'annotazione "
        "provvisoria.",
        "",
        "## Sintesi",
        "",
        "| Caso | Decisione | Claim piene | Parziali | Senza riscontro | Freeze blockers |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        comparison = entry["comparison"]
        lines.append(
            f"| `{entry['case_id']}` | **{entry['decision']['decision']}** | "
            f"{len(comparison['structurally_matching_claims'])} | "
            f"{len(comparison['partially_matching_claims'])} | "
            f"{len(comparison['unmatched_claims'])} | "
            f"{len(comparison['freeze_blockers'])} |"
        )
    lines.append("")

    for entry in entries:
        comparison = entry["comparison"]
        outcome: CaseOutcome = entry["outcome"]
        case: GoldCase = entry["case"]
        lines += [
            f"## {case.case_id}",
            "",
            f"_{case.case_context}_",
            "",
            "### Che cosa e' stato trovato",
            "",
            f"- terapie: {comparison['found_therapies'] or 'nessuna'}",
            f"- PMID: {comparison['found_pmids'] or 'nessuno'}",
            f"- NCT: {comparison['found_nct_ids'] or 'nessuno'}",
            f"- record di evidenza normalizzati: {len(outcome.graph_claims)}",
            "",
            "### Che cosa manca",
            "",
            f"- terapie: {comparison['missing_therapies'] or 'nessuna'}",
            f"- PMID: {comparison['missing_pmids'] or 'nessuno'}",
            f"- NCT: {comparison['missing_nct_ids'] or 'nessuno'}",
            "",
            "### Che cosa e' presente in piu'",
            "",
            f"- terapie: {comparison['extra_therapies'] or 'nessuna'}",
            f"- PMID: {comparison['extra_pmids'] or 'nessuno'}",
            "",
            "### Qualificatori",
            "",
            f"- confrontati sul grafo: {len(comparison['qualifiers_found'])}",
            f"- assenti o non confrontabili: {len(comparison['qualifiers_missing'])}",
            f"- non modellati dallo schema: {comparison['not_modelled_by_schema']}",
            "",
            "### Conflitti",
            "",
            _bullet_list(
                [
                    f"{c['claim_id']} / {c['dimension']}: gold '{c['gold_value']}' vs "
                    f"grafo '{c['graph_value']}'"
                    for c in comparison["conflicts"]
                ],
                empty="nessuno",
            ),
            "",
            "### Problemi di schema",
            "",
            _bullet_list(outcome.warnings, empty="nessuno"),
            "",
            "### Freeze blockers",
            "",
            _bullet_list(comparison["freeze_blockers"], empty="nessuno"),
            "",
            f"### Decisione proposta: {entry['decision']['decision']}",
            "",
            entry["decision"]["rationale"],
            "",
        ]

    lines += [
        "## Limiti dell'audit",
        "",
        "- Il fingerprint e' derivato da statistiche aggregate, non e' un hash del "
        "contenuto: due grafi con le stesse statistiche collidono.",
        "- Setting, linea di terapia, stadio ed esposizione precedente non sono "
        "modellati dallo schema. Le classificazioni corrispondenti sono euristiche "
        "testuali su `evidence_statement` e vanno lette come indizi, non come dati.",
        "- L'assenza di un PMID come nodo `Publication` non implica che la pubblicazione "
        "non esista: implica che non e' recuperabile da questo snapshot.",
        "- Nessuna decisione qui e' definitiva: tutte richiedono la seconda revisione "
        "indipendente prevista dalle note di annotazione.",
        "",
    ]
    return "\n".join(lines)

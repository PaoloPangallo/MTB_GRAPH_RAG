"""Estrazione di predizioni valutabili da un `PipelineResult`.

La pipeline produce un oggetto ricco: vista canonica, proiezione, report candidato,
report verificato, dossier, verdetti. Le metriche vogliono invece due strutture
piatte, `RetrievalPrediction` e `ReportPrediction`.

La conversione vive qui e non nel runner per una ragione precisa: e' il punto in cui
si decide *che cosa conta come recuperato* e *che cosa conta come riportato*, e quella
decisione deve essere leggibile e testabile senza eseguire la pipeline.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..pilot.audit_lib.normalize import norm_drug, norm_nct_set, norm_pmid_set, norm_text
from .contracts import ReportPrediction, RetrievalPrediction

# Chiavi dello stato terminale in cui i tool depositano i record. Allineate a
# TOOL_OUTPUTS del registry degli strumenti.
_EVIDENCE_KEYS = ("evidence_records", "drug_candidates", "trial_candidates",
                  "resistance_data", "oncokb_enrichment")


def _walk(value: Any):
    """Percorre ricorsivamente lo stato, restituendo ogni mapping incontrato."""
    if isinstance(value, Mapping):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def _collect_records(terminal_state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """I record depositati dai tool, ovunque siano annidati nello stato."""
    records: list[Mapping[str, Any]] = []
    for container in _walk(terminal_state):
        for key in _EVIDENCE_KEYS:
            value = container.get(key)
            if isinstance(value, (list, tuple)):
                records.extend(item for item in value if isinstance(item, Mapping))
    return records


def retrieval_from_result(result: Any, alias_table: Mapping[str, str]) -> RetrievalPrediction:
    """Che cosa la raccolta ha effettivamente portato dal grafo.

    Si legge dallo **stato terminale** della raccolta, non dal report: il report e' lo
    stadio successivo, e usarlo qui confonderebbe cio' che e' stato recuperato con
    cio' che e' sopravvissuto alla scrittura.
    """
    collection = result.collection
    records = _collect_records(collection.terminal_state or {})

    therapies: set[str] = set()
    pmids: set[str] = set()
    ncts: set[str] = set()
    entities: set[str] = set()

    for record in records:
        for key in ("drug", "drug_name", "therapy", "object"):
            value = record.get(key)
            if value:
                therapies.add(norm_drug(value, dict(alias_table)))
        pmids.update(norm_pmid_set(record.get("citation_id")))
        pmids.update(norm_pmid_set(record.get("pmid")))
        pmids.update(norm_pmid_set(record.get("source_id")))
        ncts.update(norm_nct_set(record.get("nct_id")))
        for key in ("molecular_profile", "variant", "gene", "subject"):
            value = record.get(key)
            if value:
                entities.add(norm_text(value))

    # Un'astensione e' tale se la raccolta non ha prodotto alcuna terapia.
    abstained = not therapies

    return RetrievalPrediction(
        case_id=result.case.case_id if hasattr(result.case, "case_id") else "",
        architecture=result.architecture_id,
        therapies=tuple(sorted(therapies - {""})),
        pmids=tuple(sorted(pmids)),
        nct_ids=tuple(sorted(ncts)),
        entities=tuple(sorted(entities - {""})),
        record_ids=tuple(
            str(record.get("record_id") or record.get("evidence_id") or "")
            for record in records
        ),
        claims=tuple(dict(record) for record in records),
        tools_called=tuple(collection.tool_path),
        planner_calls=int(collection.planner_calls or 0),
        abstained=abstained,
    )


def _applicability_by_claim(result: Any) -> dict[str, str]:
    """Applicabilita' dichiarata dal verificatore, per claim."""
    mapping: dict[str, str] = {}
    for check in result.claim_checks or ():
        identifier = getattr(check, "claim_id", None) or getattr(check, "id", None)
        applicability = getattr(check, "applicability", None)
        if identifier and applicability:
            mapping[str(identifier)] = norm_text(applicability)
    return mapping


def report_from_result(
    result: Any, branch: str, alias_table: Mapping[str, str]
) -> ReportPrediction:
    """Che cosa il report conserva del materiale recuperato."""
    text = result.report if branch.endswith("verified") else result.candidate_report
    text = text or ""

    claims = [
        {
            "claim_id": str(getattr(item, "claim_id", "") or f"{branch}::{index}"),
            "subject": norm_text(getattr(item, "subject", "")),
            "relation": norm_text(getattr(item, "relation", "")),
            "object": norm_text(getattr(item, "object", "")),
            "disease": norm_text(getattr(item, "context", "")),
            "pmid": str(getattr(item, "source_id", "") or ""),
        }
        for index, item in enumerate(result.evidence_items or ())
    ]

    verdict = result.final_verdict if branch.endswith("verified") else result.candidate_verdict
    escalated = result.escalation is not None

    return ReportPrediction(
        case_id=result.case.case_id if hasattr(result.case, "case_id") else "",
        branch=branch,
        text=text,
        claims=tuple(claims),
        cited_pmids=tuple(norm_pmid_set([claim["pmid"] for claim in claims])),
        cited_nct_ids=tuple(norm_nct_set([claim["pmid"] for claim in claims])),
        mentioned_therapies=tuple(
            sorted({norm_drug(claim["object"], dict(alias_table)) for claim in claims} - {""})
        ),
        qualifiers_present=tuple(
            sorted({claim["disease"] for claim in claims if claim["disease"]})
        ),
        abstained=not claims,
        requested_human_review=escalated or bool(getattr(verdict, "violations", ())),
        applicability_by_claim=_applicability_by_claim(result),
    )


def run_telemetry(result: Any, elapsed_ms: float) -> dict[str, Any]:
    """Tutto cio' che la specifica chiede di registrare per ogni run."""
    collection = result.collection
    return {
        "run_id": result.run_id,
        "architecture": result.architecture_id,
        "orchestration_mode": result.orchestration_mode,
        "tool_path": list(collection.tool_path),
        "planner_calls": int(collection.planner_calls or 0),
        "planner_elapsed_ms": int(collection.planner_elapsed_ms or 0),
        "planning_mode": collection.planning_mode,
        "fallback_reason": collection.fallback_reason,
        "mandatory_tools": list(collection.mandatory_tools),
        "missing_mandatory_tools": list(collection.missing_mandatory_tools),
        "retrieval_tool_calls": len(collection.tool_call_timings or ()),
        "latency_by_stage": {
            str(timing.get("tool", f"step_{index}")): timing.get("elapsed_ms")
            for index, timing in enumerate(collection.tool_call_timings or ())
        },
        "total_elapsed_ms": round(elapsed_ms, 2),
        "structural_verdict": {
            "candidate_violations": len(getattr(result.candidate_verdict, "violations", ()) or ()),
            "final_violations": len(getattr(result.final_verdict, "violations", ()) or ()),
            "dossier_violations": len(getattr(result.dossier_verdict, "violations", ()) or ()),
        },
        "source_verifications": len(result.claim_checks or ()),
        "repair_attempts": int(result.repair_attempts or 0),
        "escalated": result.escalation is not None,
        "ledger_valid": bool(result.ledger_valid),
        "replay_fidelity": getattr(result.canonical_view, "replay_fidelity", None),
        "records_in": getattr(result.canonical_view, "records_in", None),
        "records_out": getattr(result.canonical_view, "records_out", None),
    }

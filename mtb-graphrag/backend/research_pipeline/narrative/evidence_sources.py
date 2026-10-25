"""Presentation-only source projection; never changes evidence admission."""

from typing import Any


def paper_sources(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind each admitted quotation to its own document and SourceUnit.

    If record-level evidence is present, it is authoritative. Never attach a
    representative quote to the graph's declared document instead.
    """
    records = entry.get("accepted_evidence_records") or []
    if records:
        items = [record for record in records if isinstance(record, dict)]
    else:
        items = [{
            "paper_id": entry.get("representative_document_id") or entry.get("document_id"),
            "source_unit_id": entry.get("quote_source_unit_id"),
            "quote": entry.get("quote"),
            "quote_valid": entry.get("quote_valid"),
            "source_unit_text": entry.get("source_unit_text"),
            "support_level": entry.get("support_level"),
        }]
    sources = []
    seen = set()
    for record in items:
        paper_id = str(record.get("document_id") or record.get("paper_id") or "").strip()
        if not paper_id:
            continue
        unit = str(record.get("source_unit_id") or "").strip()
        quote = record.get("quote") or record.get("author_claim_quote")
        authenticated = (record.get("quote_valid") is True or
                         (record.get("quote_valid") is not False and
                          record.get("presentation_state") == "VALIDATED_QUOTE"))
        available = authenticated and isinstance(quote, str) and bool(quote.strip()) and bool(unit)
        support = record.get("candidate_support") or {}
        support_result = support.get("result") or record.get("support_result") or record.get("support_level")
        key = (paper_id, unit, quote if available else None, record.get("evidence_id"), support_result)
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "paper_id": paper_id,
            "source_unit_id": unit if available else "",
            "quote_available": available,
            "validated_quote": quote if available else None,
            "source_unit_text": record.get("source_unit_text") if available else None,
            "evidence_id": record.get("evidence_id"),
            "support_result": support_result,
        })
    return sources

"""Human-readable projection of the canonical dossier.

This module is deliberately deterministic and has no model, retrieval, or
clinical decision logic.  It renders information already present in the
canonical dossier so a clinician can inspect the case without reading JSON.
"""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("label") or value.get("normalized_value") or value.get("id"))
    return _text(value)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def _join(value: Any) -> str:
    parts = []
    for item in _list(value):
        label = _label(item) if isinstance(item, dict) else _text(item)
        if label:
            parts.append(label)
    return ", ".join(parts)


def _bullet(label: str, value: Any) -> str:
    rendered = _join(value) if isinstance(value, (list, tuple, dict)) else _text(value)
    return f"- **{label}:** {rendered or 'non disponibile'}"


def render_dossier_markdown(
    dossier: dict[str, Any] | None,
    narrative: dict[str, Any] | None = None,
    presentation_mode: str | None = None,
    verification: dict[str, Any] | None = None,
) -> str:
    """Render the dossier as a clinician-oriented Markdown document."""
    dossier = dossier or {}
    context = dossier.get("case_summary") or {}
    lines = ["# Dossier clinico-documentale", ""]
    lines.extend([
        "## Caso", "",
        _bullet("Case ID", context.get("case_id") or dossier.get("case_id")),
        _bullet("Malattia", context.get("disease")),
        _bullet("Biomarcatori", context.get("biomarkers") or context.get("gene")),
        _bullet("Alterazione", context.get("variant") or context.get("alteration")),
        _bullet("Intervento", context.get("intervention")),
        "",
    ])
    retrieval = dossier.get("retrieval_summary") or {}
    if retrieval:
        lines.extend([
            "## Recupero delle evidenze", "",
            _bullet("Candidate totali", retrieval.get("total_candidates")),
            _bullet("Candidate selezionate", retrieval.get("selected_total")),
            _bullet("Paper", retrieval.get("paper_candidates")),
            _bullet("Trial", retrieval.get("trial_candidates")),
            _bullet("KG_ONLY", retrieval.get("kg_only_candidates")),
            "",
        ])

    paper_entries = [e for e in dossier.get("paper_evidence") or [] if isinstance(e, dict)]
    lines.extend(["## Evidenza dai paper", ""])
    if not paper_entries:
        lines.append("Nessuna evidenza documentale da paper disponibile.")
    for index, entry in enumerate(paper_entries, 1):
        lines.extend([
            f"### Paper {index}",
            _bullet("Candidate", entry.get("candidate_id")),
            _bullet("Relazione", entry.get("relation")),
            _bullet("Stato", entry.get("support_level") or entry.get("support_status")),
            _bullet("Documento", entry.get("document_id") or entry.get("requested_document_id")),
            _bullet("PMCID", entry.get("pmcid")),
            _bullet("SourceUnit", entry.get("quote_source_unit_id")),
        ])
        quote = _text(entry.get("quote")) if entry.get("quote_valid") else ""
        lines.append(f'- **Quote validata:** “{quote}”' if quote else "- **Quote validata:** non disponibile")
        fields = entry.get("support_fields") or {}
        if fields:
            lines.append(_bullet("Supporto per campo", "; ".join(f"{k}={v}" for k, v in fields.items())))
        if entry.get("support_reason"):
            lines.append(_bullet("Motivazione", entry["support_reason"]))
        lines.append("")

    trial_entries = [e for e in dossier.get("clinical_trials") or [] if isinstance(e, dict)]
    lines.extend(["## Trial clinici", ""])
    if not trial_entries:
        lines.append("Nessun trial clinico associato disponibile.")
    for index, entry in enumerate(trial_entries, 1):
        interventions = [item.get("name") if isinstance(item, dict) else item for item in _list(entry.get("interventions"))]
        lines.extend([
            f"### Trial {index}",
            _bullet("Candidate", entry.get("candidate_id")),
            _bullet("NCT", entry.get("nct_id")),
            _bullet("Titolo", entry.get("title")),
            _bullet("Condizioni", entry.get("conditions")),
            _bullet("Interventi", interventions),
            _bullet("Fase", entry.get("phase")),
            _bullet("Stato", entry.get("status") or entry.get("recruitment_status")),
            _bullet("Risoluzione", entry.get("trial_resolution_status")),
            _bullet("Eleggibilità", entry.get("eligibility_status") or "NOT_EVALUATED"),
            _bullet("Interpretazione", entry.get("evidence_interpretation") or "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"),
            "",
        ])

    kg_entries = [e for e in dossier.get("kg_only_relations") or [] if isinstance(e, dict)]
    lines.extend(["## Relazioni Knowledge Graph", ""])
    if not kg_entries:
        lines.append("Nessuna relazione KG_ONLY disponibile.")
    for index, entry in enumerate(kg_entries, 1):
        provenance = entry.get("graph_provenance") or {}
        lines.extend([
            f"### Relazione KG {index}",
            _bullet("Candidate", entry.get("candidate_id")),
            _bullet("Soggetto", entry.get("subject")),
            _bullet("Relazione", entry.get("relation")),
            _bullet("Oggetto", entry.get("object")),
            _bullet("Malattia/contesto", entry.get("disease_context")),
            _bullet("Database sorgente", entry.get("source_database")),
            _bullet("Verifica", entry.get("verification_status") or "KG_ONLY"),
            _bullet("Provenienza documentale", entry.get("document_provenance") or "NOT_AVAILABLE"),
            _bullet("Graph path", provenance.get("graph_path")),
            _bullet("Graph edge", provenance.get("edge_ids")),
            "",
        ])

    limitations = dossier.get("limitations") or []
    lines.extend(["## Limitazioni", ""])
    lines.extend(f"- {item}" for item in limitations if item)
    if not limitations:
        lines.append("Nessuna limitazione registrata.")
    lines.append("")

    if narrative:
        lines.extend(["## Sintesi narrativa verificata", "", _text(narrative.get("narrative_summary")), ""])
        for entry in narrative.get("candidate_narratives") or []:
            if isinstance(entry, dict):
                lines.extend([f"### {entry.get('candidate_id', 'Candidate')}", _text(entry.get("text")), ""])
        if narrative.get("limitations_summary"):
            lines.extend(["### Limitazioni narrative", _text(narrative["limitations_summary"]), ""])
        if narrative.get("closing_note"):
            lines.extend([_text(narrative["closing_note"]), ""])
    else:
        lines.extend(["## Presentazione", "", "La narrativa non è disponibile; viene mostrato il dossier strutturato.", ""])

    if presentation_mode:
        lines.extend([f"**Modalità di presentazione:** `{presentation_mode}`", ""])
    if verification and verification.get("status"):
        lines.extend([f"**Verifica narrativa:** `{verification['status']}`", ""])
    lines.append("_Questa scheda è informativa e non costituisce una raccomandazione terapeutica._")
    return "\n".join(lines)

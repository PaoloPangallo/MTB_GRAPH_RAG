"""Rendering deterministico del report candidato dalla proiezione.

Il renderer non aggiunge conoscenza: emette esattamente i record ammessi dalla
proiezione, con le loro citazioni, e nient'altro. Non trasforma evidenze in
raccomandazioni e non elimina conflitti — li espone.
"""

from __future__ import annotations

from backend.pipeline.control.claim_grammar import citation_token, claim_text
from backend.pipeline.control.contracts import Projection

RENDERER_VERSION = "candidate/1.0"


def render_candidate(projection: Projection) -> str:
    admitted = projection.admitted
    if not admitted:
        return (
            f"Caso: {projection.case_label}.\n"
            "Nessuna evidenza candidata disponibile dopo la proiezione."
        )

    lines = [f"Caso: {projection.case_label}.", "Evidenze candidate:"]
    for record in admitted:
        line = f"- {claim_text(record.claim)} {citation_token(record.required_citation)}"
        if record.conflict_annotations:
            fields = ", ".join(a.field_name for a in record.conflict_annotations)
            # Il conflitto viene esposto, non risolto: nasconderlo priverebbe
            # il MTB di un disaccordo fra fonti che gli serve vedere.
            line += f" — conflitto fra osservazioni su: {fields}."
        lines.append(line)
    return "\n".join(lines)


def candidate_payload(projection: Projection, report: str) -> dict:
    return {
        "renderer_version": RENDERER_VERSION,
        "records_used": sorted(projection.admitted_ids),
        "citations": sorted(
            record.required_citation for record in projection.admitted if record.required_citation
        ),
        "claims_rendered": len(projection.admitted),
        "characters": len(report),
    }

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import EscatAssessmentEvent


AUDIT_ACTIONS = frozenset(
    {
        "DRAFT_CREATED",
        "FIELD_PREFILLED",
        "FIELD_EDITED",
        "CURATOR_SET",
        "RATIONALE_SET",
        "STATUS_CHANGED",
        "SOURCE_ATTACHED",
        "PASSAGE_ATTACHED",
        "RULE_SELECTED",
        "ASSESSMENT_VALIDATED",
        "ASSESSMENT_REJECTED",
        "ASSESSMENT_SUPERSEDED",
    }
)


def make_event(
    assessment_id: str,
    actor: str,
    action: str,
    *,
    field: str | None = None,
    previous_value: Any = None,
    new_value: Any = None,
    reason: str | None = None,
    rationale: str | None = None,
) -> EscatAssessmentEvent:
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"unsupported audit action: {action}")
    explanation = rationale or reason
    return EscatAssessmentEvent(
        event_id=f"EV-{uuid4().hex}",
        assessment_id=assessment_id,
        timestamp=datetime.now(timezone.utc),
        actor=actor,
        action=action,
        field=field,
        previous_value=previous_value,
        new_value=new_value,
        reason=explanation,
        rationale=explanation,
    )


def append_event(path: Path, event: EscatAssessmentEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def read_events(path: Path, assessment_id: str | None = None) -> list[EscatAssessmentEvent]:
    if not path.exists():
        return []
    events = [
        EscatAssessmentEvent.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if assessment_id is None:
        return events
    return [event for event in events if event.assessment_id == assessment_id]

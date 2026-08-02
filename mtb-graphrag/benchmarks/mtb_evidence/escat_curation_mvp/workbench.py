from __future__ import annotations

import argparse
import json
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import append_event, make_event, read_events
from .io import read_json, write_json
from .models import ASSESSMENT_STATUSES, EscatAssessmentRecord, EscatRuleSet
from .pilot import generate_pilot
from .prefill import create_draft, load_active_claims, repository_root
from .validation import transition_status, validate_assessment


MUTABLE_FIELDS = {item.name for item in fields(EscatAssessmentRecord) if item.init} - {"assessment_id", "claim_id", "framework", "created_at", "assessment_status", "curated_at"}
SUPERSEDABLE_STATUSES = frozenset({"CURATED", "REJECTED", "CONFLICTING_EVIDENCE", "NOT_APPLICABLE"})


def _record_path(workspace: Path, assessment_id: str) -> Path:
    return workspace / "assessments" / f"{assessment_id}.json"


def _load(workspace: Path, assessment_id: str) -> EscatAssessmentRecord:
    return EscatAssessmentRecord.from_dict(read_json(_record_path(workspace, assessment_id)))


def _save(workspace: Path, record: EscatAssessmentRecord) -> None:
    write_json(_record_path(workspace, record.assessment_id), record.to_dict())


def _log(workspace: Path, record: EscatAssessmentRecord, action: str, actor: str, *, field: str | None = None, previous_value: Any = None, new_value: Any = None, rationale: str | None = None) -> None:
    append_event(workspace / "assessment_events.jsonl", make_event(record.assessment_id, actor, action, field=field, previous_value=previous_value, new_value=new_value, rationale=rationale or action))


def _ruleset(path: Path | None) -> EscatRuleSet:
    return EscatRuleSet.from_dict(read_json(path)) if path else EscatRuleSet()


def _parse_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _error(message: str, **extra: Any) -> int:
    print(json.dumps({"valid": False, "error": message, **extra}, ensure_ascii=False, indent=2))
    return 2


def export_dossier(record: EscatAssessmentRecord) -> dict[str, Any]:
    return {"clinical_actionability": {"framework": "ESCAT", "status": record.assessment_status, "tier": record.tier, "subtier": record.subtier, "origin": "MANUAL_CURATION", "framework_version": record.framework_version, "missing_requirements": list(record.missing_requirements), "sources": list(record.supporting_sources), "curator": record.curator, "curated_at": record.curated_at.isoformat() if record.curated_at else None}}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline auditable ESCAT curation workbench")
    p.add_argument("--workspace", type=Path, default=Path("benchmarks/mtb_evidence/escat_curation_mvp/workspace"))
    p.add_argument("--repo-root", type=Path, default=repository_root())
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list-claims")
    claim = sub.add_parser("show-claim"); claim.add_argument("claim_id")
    create = sub.add_parser("create-draft"); create.add_argument("claim_id")
    for name in ("show-draft", "show-missing-fields", "validate-assessment", "export-assessment", "export-dossier", "show-history"):
        q = sub.add_parser(name); q.add_argument("assessment_id")
        if name == "validate-assessment": q.add_argument("--ruleset", type=Path)
    edit = sub.add_parser("edit-field"); edit.add_argument("assessment_id"); edit.add_argument("field"); edit.add_argument("value"); edit.add_argument("--actor", default="offline-curator"); edit.add_argument("--ruleset", type=Path)
    curator = sub.add_parser("set-curator"); curator.add_argument("assessment_id"); curator.add_argument("curator"); curator.add_argument("--actor", default="offline-curator")
    rationale = sub.add_parser("set-rationale"); rationale.add_argument("assessment_id"); rationale.add_argument("rationale"); rationale.add_argument("--actor", default="offline-curator")
    status = sub.add_parser("set-status"); status.add_argument("assessment_id"); status.add_argument("status", choices=sorted(ASSESSMENT_STATUSES)); status.add_argument("--actor", default="offline-curator"); status.add_argument("--ruleset", type=Path)
    for name in ("attach-source", "attach-passage"):
        q = sub.add_parser(name); q.add_argument("assessment_id"); q.add_argument("value"); q.add_argument("--actor", default="offline-curator")
    q = sub.add_parser("select-rule"); q.add_argument("assessment_id"); q.add_argument("rule_id"); q.add_argument("--ruleset", type=Path); q.add_argument("--actor", default="offline-curator")
    reject = sub.add_parser("reject-assessment"); reject.add_argument("assessment_id"); reject.add_argument("rationale"); reject.add_argument("--actor", default="offline-curator")
    supersede = sub.add_parser("supersede-assessment"); supersede.add_argument("assessment_id"); supersede.add_argument("--new-assessment-id", required=True); supersede.add_argument("--actor", default="offline-curator")
    seed = sub.add_parser("seed-pilot"); seed.add_argument("--output-dir", type=Path, default=Path("benchmarks/mtb_evidence/escat_curation_mvp/data"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.repo_root; workspace = args.workspace
    workspace.mkdir(parents=True, exist_ok=True)
    claims = load_active_claims(root)
    try:
        if args.command == "list-claims":
            print(json.dumps([{"claim_id": key, "claim_domain": value.get("claim_domain"), "direction": value.get("direction")} for key, value in claims.items()], ensure_ascii=False, indent=2)); return 0
        if args.command == "show-claim":
            if args.claim_id not in claims: return _error("CLAIM_NOT_FOUND")
            print(json.dumps(claims[args.claim_id], ensure_ascii=False, indent=2)); return 0
        if args.command == "seed-pilot":
            drafts = generate_pilot(args.output_dir, root=root); print(json.dumps({"drafts": len(drafts), "output_dir": str(args.output_dir)}, indent=2)); return 0
        if args.command == "create-draft":
            draft = create_draft(args.claim_id, root=root); _save(workspace, draft.assessment)
            _log(workspace, draft.assessment, "DRAFT_CREATED", "offline-workbench", new_value=draft.assessment.to_dict(), rationale="draft created")
            for field_name, value in draft.prefilled_fields.items():
                _log(workspace, draft.assessment, "FIELD_PREFILLED", "offline-workbench", field=field_name, new_value=value, rationale="prefilled from local source")
            print(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2)); return 0
        record = _load(workspace, args.assessment_id)
        if args.command in {"show-draft", "export-assessment"}:
            print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command == "show-missing-fields":
            print(json.dumps(record.missing_requirements, ensure_ascii=False, indent=2)); return 0
        if args.command == "show-history":
            print(json.dumps([event.to_dict() for event in read_events(workspace / "assessment_events.jsonl", record.assessment_id)], ensure_ascii=False, indent=2)); return 0
        if args.command == "export-dossier":
            print(json.dumps(export_dossier(record), ensure_ascii=False, indent=2)); return 0
        if args.command == "validate-assessment":
            result = validate_assessment(record, _ruleset(args.ruleset)); _log(workspace, record, "ASSESSMENT_VALIDATED", "offline-curator", new_value=result.to_dict(), rationale="assessment validation executed")
            print(json.dumps(result.to_dict(), indent=2)); return 0 if result.valid else 2
        if args.command == "edit-field":
            if args.field not in MUTABLE_FIELDS: return _error("FIELD_NOT_EDITABLE", field=args.field)
            value = _parse_value(args.value)
            if args.field in {"tier", "subtier"} and value is not None and not _ruleset(args.ruleset).structurally_available: return _error("OFFICIAL_RULESET_NOT_AVAILABLE")
            previous = getattr(record, args.field); updated = replace(record, **{args.field: value}); _save(workspace, updated)
            _log(workspace, updated, "FIELD_EDITED", args.actor, field=args.field, previous_value=previous, new_value=value, rationale=f"edited field {args.field}")
            print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command == "set-curator":
            if not args.curator.strip(): return _error("CURATOR_REQUIRED")
            updated = replace(record, curator=args.curator); _save(workspace, updated); _log(workspace, updated, "CURATOR_SET", args.actor, field="curator", previous_value=record.curator, new_value=args.curator, rationale="curator set")
            print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command == "set-rationale":
            if not args.rationale.strip(): return _error("RATIONALE_REQUIRED")
            updated = replace(record, rationale=args.rationale); _save(workspace, updated); _log(workspace, updated, "RATIONALE_SET", args.actor, field="rationale", previous_value=record.rationale, new_value=args.rationale, rationale=args.rationale)
            print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command == "set-status":
            if args.status == "SUPERSEDED": return _error("SUPERSEDED_REQUIRES_SUPERSEDE_COMMAND")
            try: transition_status(record.assessment_status, args.status)
            except ValueError:
                _log(workspace, record, "STATUS_CHANGED", args.actor, field="assessment_status", previous_value=record.assessment_status, new_value=args.status, rationale="INVALID_STATUS_TRANSITION"); return _error("INVALID_STATUS_TRANSITION")
            updated = replace(record, assessment_status=args.status, curated_at=datetime.now(timezone.utc) if args.status == "CURATED" else record.curated_at)
            if args.status == "CURATED":
                result = validate_assessment(updated, _ruleset(args.ruleset))
                if not result.valid:
                    _log(workspace, record, "STATUS_CHANGED", args.actor, field="assessment_status", previous_value=record.assessment_status, new_value=args.status, rationale="STATUS_VALIDATION_FAILED"); return _error("STATUS_VALIDATION_FAILED", errors=result.errors)
            _save(workspace, updated); _log(workspace, updated, "STATUS_CHANGED", args.actor, field="assessment_status", previous_value=record.assessment_status, new_value=args.status, rationale="status changed")
            print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command in {"attach-source", "attach-passage"}:
            value = _parse_value(args.value)
            if isinstance(value, str): value = {"source_id": value} if args.command == "attach-source" else {"text": value}
            if not isinstance(value, dict): return _error("ATTACHMENT_MUST_BE_OBJECT")
            required = "source_id" if args.command == "attach-source" else "text"
            if not value.get(required): return _error(f"{required.upper()}_REQUIRED")
            field_name = "supporting_sources" if args.command == "attach-source" else "supporting_passages"; previous = list(getattr(record, field_name)); updated = replace(record, **{field_name: previous + [value]}); _save(workspace, updated)
            _log(workspace, updated, "SOURCE_ATTACHED" if field_name == "supporting_sources" else "PASSAGE_ATTACHED", args.actor, field=field_name, previous_value=previous, new_value=value, rationale=f"attached {field_name}")
            print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command == "select-rule":
            ruleset = _ruleset(args.ruleset)
            if not ruleset.structurally_available: return _error("OFFICIAL_RULESET_NOT_AVAILABLE")
            rule = next((item for item in ruleset.rules if item.rule_id == args.rule_id), None)
            if rule is None: return _error("RULE_ID_NOT_FOUND")
            if args.rule_id in record.rule_ids: return _error("RULE_ALREADY_SELECTED")
            updated = replace(record, rule_ids=record.rule_ids + [args.rule_id], framework_version=ruleset.version); _save(workspace, updated)
            _log(workspace, updated, "RULE_SELECTED", args.actor, field="rule_ids", previous_value=record.rule_ids, new_value=updated.rule_ids, rationale="rule selected; tier remains curator-assigned")
            print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command == "reject-assessment":
            if not args.rationale.strip(): return _error("RATIONALE_REQUIRED")
            try: transition_status(record.assessment_status, "REJECTED")
            except ValueError:
                _log(workspace, record, "STATUS_CHANGED", args.actor, field="assessment_status", previous_value=record.assessment_status, new_value="REJECTED", rationale="INVALID_STATUS_TRANSITION")
                return _error("INVALID_STATUS_TRANSITION")
            updated = replace(record, assessment_status="REJECTED", rationale=args.rationale); _save(workspace, updated)
            _log(workspace, updated, "STATUS_CHANGED", args.actor, field="assessment_status", previous_value=record.assessment_status, new_value="REJECTED", rationale=args.rationale)
            _log(workspace, updated, "ASSESSMENT_REJECTED", args.actor, previous_value=record.to_dict(), new_value=updated.to_dict(), rationale=args.rationale)
            print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
        if args.command == "supersede-assessment":
            if record.assessment_status not in SUPERSEDABLE_STATUSES: return _error("ASSESSMENT_NOT_SUPERSEDABLE")
            if _record_path(workspace, args.new_assessment_id).exists(): return _error("REPLACEMENT_ID_ALREADY_EXISTS")
            event = make_event(record.assessment_id, args.actor, "ASSESSMENT_SUPERSEDED", previous_value=record.to_dict(), new_value=args.new_assessment_id, rationale="assessment superseded")
            write_json(workspace / "assessment_versions" / record.assessment_id / f"{event.event_id}.json", record.to_dict())
            old = replace(record, assessment_status="SUPERSEDED")
            replacement = replace(record, assessment_id=args.new_assessment_id, assessment_status="DRAFT", framework_version=None, tier=None, subtier=None, rule_ids=[], curator=None, rationale=None, curated_at=None, supersedes_assessment_id=record.assessment_id, reason_codes=list(dict.fromkeys(record.reason_codes + ["SUPERSEDES_PREVIOUS_ASSESSMENT"])))
            _save(workspace, old); _save(workspace, replacement); append_event(workspace / "assessment_events.jsonl", event)
            _log(workspace, replacement, "DRAFT_CREATED", args.actor, new_value=replacement.to_dict(), rationale="replacement draft created")
            print(json.dumps(replacement.to_dict(), ensure_ascii=False, indent=2)); return 0
        return _error("UNKNOWN_COMMAND")
    except (KeyError, FileNotFoundError) as exc:
        return _error("NOT_FOUND", detail=str(exc))
    except ValueError as exc:
        return _error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

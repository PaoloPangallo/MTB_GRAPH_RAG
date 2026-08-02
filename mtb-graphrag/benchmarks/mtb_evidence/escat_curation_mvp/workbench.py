from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .audit import append_event, make_event, read_events
from .io import read_json, write_json
from .models import EscatAssessmentRecord, EscatRuleSet
from .pilot import generate_pilot
from .prefill import create_draft, load_active_claims, repository_root
from .validation import validate_assessment


def _record_path(workspace: Path, assessment_id: str) -> Path:
    return workspace / "assessments" / f"{assessment_id}.json"


def _load(workspace: Path, assessment_id: str) -> EscatAssessmentRecord:
    return EscatAssessmentRecord.from_dict(read_json(_record_path(workspace, assessment_id)))


def _save(workspace: Path, record: EscatAssessmentRecord) -> None:
    write_json(_record_path(workspace, record.assessment_id), record.to_dict())


def _log(workspace: Path, record: EscatAssessmentRecord, action: str, actor: str, **kwargs: Any) -> None:
    append_event(workspace / "assessment_events.jsonl", make_event(record.assessment_id, actor, action, **kwargs))


def export_dossier(record: EscatAssessmentRecord) -> dict[str, Any]:
    return {"clinical_actionability": {
        "framework": "ESCAT", "status": "INCOMPLETE" if record.tier is None else record.assessment_status,
        "tier": record.tier, "subtier": record.subtier, "origin": "MANUAL_CURATION",
        "framework_version": record.framework_version, "missing_requirements": record.missing_requirements,
        "sources": record.supporting_sources, "curator": record.curator,
        "curated_at": record.curated_at.isoformat() if record.curated_at else None,
    }}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline auditable ESCAT curation workbench")
    p.add_argument("--workspace", type=Path, default=Path("benchmarks/mtb_evidence/escat_curation_mvp/workspace"))
    p.add_argument("--repo-root", type=Path, default=repository_root())
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list-claims")
    claim = sub.add_parser("show-claim"); claim.add_argument("claim_id")
    create = sub.add_parser("create-draft"); create.add_argument("claim_id")
    for name in ("show-missing-fields", "validate-assessment", "export-assessment", "show-history"):
        q = sub.add_parser(name); q.add_argument("assessment_id")
    for name in ("attach-source", "attach-passage"):
        q = sub.add_parser(name); q.add_argument("assessment_id"); q.add_argument("value"); q.add_argument("--actor", default="offline-curator")
    q = sub.add_parser("select-rule"); q.add_argument("assessment_id"); q.add_argument("rule_id"); q.add_argument("--ruleset", type=Path); q.add_argument("--actor", default="offline-curator")
    q = sub.add_parser("seed-pilot"); q.add_argument("--output-dir", type=Path, default=Path("benchmarks/mtb_evidence/escat_curation_mvp/data"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.repo_root
    workspace = args.workspace
    workspace.mkdir(parents=True, exist_ok=True)
    claims = load_active_claims(root)
    if args.command == "list-claims":
        print(json.dumps([{"claim_id": key, "claim_domain": value.get("claim_domain"), "direction": value.get("direction")} for key, value in claims.items()], ensure_ascii=False, indent=2)); return 0
    if args.command == "show-claim":
        print(json.dumps(claims[args.claim_id], ensure_ascii=False, indent=2)); return 0
    if args.command == "seed-pilot":
        drafts = generate_pilot(args.output_dir, root=root); print(json.dumps({"drafts": len(drafts), "output_dir": str(args.output_dir)}, indent=2)); return 0
    if args.command == "create-draft":
        draft = create_draft(args.claim_id, root=root); _save(workspace, draft.assessment); _log(workspace, draft.assessment, "DRAFT_CREATED", "offline-workbench", new_value=draft.to_dict()); print(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2)); return 0

    record = _load(workspace, args.assessment_id)
    if args.command == "show-missing-fields":
        print(json.dumps(record.missing_requirements, ensure_ascii=False, indent=2)); return 0
    if args.command == "validate-assessment":
        ruleset = EscatRuleSet.from_dict(read_json(args.ruleset)) if getattr(args, "ruleset", None) else EscatRuleSet()
        result = validate_assessment(record, ruleset); print(json.dumps(result.to_dict(), indent=2)); return 0 if result.valid else 2
    if args.command == "export-assessment":
        print(json.dumps(export_dossier(record), ensure_ascii=False, indent=2)); return 0
    if args.command == "show-history":
        print(json.dumps([event.to_dict() for event in read_events(workspace / "assessment_events.jsonl", record.assessment_id)], ensure_ascii=False, indent=2)); return 0
    if args.command in {"attach-source", "attach-passage"}:
        try: value = json.loads(args.value)
        except json.JSONDecodeError: value = {"text": args.value} if args.command == "attach-passage" else {"source_id": args.value}
        field = "supporting_sources" if args.command == "attach-source" else "supporting_passages"
        previous = list(getattr(record, field)); updated = replace(record, **{field: previous + [value]}); _save(workspace, updated)
        _log(workspace, updated, "SOURCE_ATTACHED" if field == "supporting_sources" else "PASSAGE_ATTACHED", args.actor, field=field, previous_value=previous, new_value=getattr(updated, field)); print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
    if args.command == "select-rule":
        ruleset = EscatRuleSet.from_dict(read_json(args.ruleset)) if args.ruleset else EscatRuleSet()
        if not ruleset.available or not any(rule.rule_id == args.rule_id for rule in ruleset.rules): print(json.dumps({"valid": False, "error": "OFFICIAL_RULESET_NOT_AVAILABLE"}, indent=2)); return 2
        updated = replace(record, rule_ids=record.rule_ids + [args.rule_id], framework_version=ruleset.version); _save(workspace, updated); _log(workspace, updated, "RULE_SELECTED", args.actor, field="rule_ids", previous_value=record.rule_ids, new_value=updated.rule_ids); print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)); return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

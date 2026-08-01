"""Standalone validator for G1.1 response files; it never assigns labels."""
from __future__ import annotations

import argparse
import json

from .campaign_tooling_g1_1 import CAMPAIGN_ROOT, DEFAULT_RUNTIME_MANIFEST, ToolingError, load_runtime_manifest, resolve_batch, validate_responses, verify_packet, resolve_manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate G1.1 annotation responses")
    parser.add_argument("--reviewer", required=True, choices=["reviewer_A", "reviewer_B"])
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--mode", required=True, choices=["partial", "complete"])
    args = parser.parse_args(argv)
    try:
        manifest = load_runtime_manifest(DEFAULT_RUNTIME_MANIFEST)
        batch = resolve_batch(manifest, args.reviewer, args.batch_id)
        verify_packet(batch)
        output = resolve_manifest_path(batch["output_path"], CAMPAIGN_ROOT / args.reviewer / "responses")
        audit = resolve_manifest_path(batch["audit_log_path"], CAMPAIGN_ROOT / args.reviewer / "audit_logs")
        result = validate_responses(batch, output, audit, args.mode)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["passed"] else 1
    except ToolingError as exc:
        print(json.dumps({"failure_class": exc.failure_class, "error": str(exc)}, ensure_ascii=False), file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

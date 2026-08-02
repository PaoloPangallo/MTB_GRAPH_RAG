from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .io import write_jsonl
from .prefill import create_draft, load_availability, repository_root


def partially_assignable_claim_ids(root: Path | None = None) -> list[str]:
    return [
        claim_id
        for claim_id, row in load_availability(root).items()
        if row.get("assessment_status") == "PARTIALLY_ASSIGNABLE"
    ]


def generate_pilot(output_dir: Path, root: Path | None = None) -> list[dict[str, Any]]:
    root = root or repository_root()
    output_dir.mkdir(parents=True, exist_ok=True)
    claim_ids = partially_assignable_claim_ids(root)
    drafts = [create_draft(claim_id, root=root).to_dict() for claim_id in claim_ids]
    write_jsonl(output_dir / "pilot_drafts.jsonl", drafts)

    availability = load_availability(root)
    selected = [availability[claim_id] for claim_id in claim_ids]
    with (output_dir / "pilot_data_availability.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0]) if selected else ["claim_id"])
        writer.writeheader()
        writer.writerows(selected)

    with (output_dir / "pilot_missing_requirements.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["claim_id", "assessment_status", "missing_requirement"])
        writer.writeheader()
        for draft in drafts:
            assessment = draft["assessment"]
            for requirement in assessment["missing_requirements"]:
                writer.writerow(
                    {
                        "claim_id": assessment["claim_id"],
                        "assessment_status": assessment["assessment_status"],
                        "missing_requirement": requirement,
                    }
                )
    return drafts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate offline ESCAT curation drafts")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    drafts = generate_pilot(args.output_dir)
    print(f"drafts={len(drafts)}")

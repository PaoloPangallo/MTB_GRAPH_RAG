"""Mappa documentale delle tre fonti: che cosa contengono, parte per parte.

La mappa e' il passaggio che rende verificabile la decisione strutturale. Dire
«questa fonte contiene clinico e preclinico» senza dire quali coorti, quali
modelli e quali saggi lascerebbe la decisione indistinguibile da una
impressione.

Ogni mappa porta anche le risposte esplicite alle dieci domande della fase,
comprese quelle scomode: se i farmaci testati in laboratorio siano stati
somministrati ai pazienti, e se le alterazioni fossero requisiti di arruolamento
o reperti successivi. Confondere le due cose e' il modo piu' diretto di
trasformare un reperto in un criterio di inclusione che non e' mai esistito.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import FINDINGS  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    REVIEW_VERSION,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    verification = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.output / "source_access_verification.jsonl")
    }

    rows: list[dict[str, Any]] = []
    for finding in FINDINGS:
        access = verification.get(finding.parent_unit_id, {})
        document_map = dict(finding.document_map)
        rows.append(
            {
                "profile_unit_id": finding.parent_unit_id,
                "canonical_source_id": finding.canonical_source_id,
                "pmid": finding.pmid,
                "pmc_id": finding.pmc_id,
                "availability": finding.availability,
                "document_hash": access.get("document_hash", ""),
                "locators_verified": access.get("locators_verified", 0),
                "locator_count": access.get("locator_count", 0),
                "document_map": document_map,
                "answers": dict(finding.answers),
                "has_clinical_component": bool(document_map.get("clinical_cohorts")),
                "has_preclinical_component": bool(
                    document_map.get("cell_models") or document_map.get("animal_models")
                ),
                "clinical_cohort_count": len(document_map.get("clinical_cohorts") or ()),
                "subgroup_count": len(document_map.get("subgroups") or ()),
                "cell_model_count": len(document_map.get("cell_models") or ()),
                "animal_model_count": len(document_map.get("animal_models") or ()),
                "in_vitro_drug_count": len(document_map.get("drugs_tested_in_vitro") or ()),
                "in_vivo_drug_count": len(document_map.get("drugs_tested_in_vivo") or ()),
                "limitations": list(finding.limitations),
                "created_at": created_at,
                "review_version": REVIEW_VERSION,
            }
        )

    rows.sort(key=lambda row: row["profile_unit_id"])
    write_jsonl(args.output / "source_document_maps.jsonl", rows)

    for row in rows:
        print(
            f"{row['profile_unit_id']}: coorti {row['clinical_cohort_count']} | "
            f"sottogruppi {row['subgroup_count']} | modelli cellulari "
            f"{row['cell_model_count']} | modelli animali {row['animal_model_count']} | "
            f"preclinico: {row['has_preclinical_component']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

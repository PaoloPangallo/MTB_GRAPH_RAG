"""Screening leggero delle fonti per rischio di split non rilevato.

Serve a **quantificare** il rischio residuo, non a risolverlo. Nessuna unita'
viene modificata, nessun profilo viene generato, nessuna revisione viene
prodotta. L'output e' una lista di candidati con i segnali che li hanno accesi.

Lo screening copre tutte e 102 le fonti, non solo quelle a statement singolo. La
ragione e' il caso PMID 22277784: aveva dieci statement ed era invisibile al
rilevatore in produzione, quindi limitare lo screening alle single-statement
riprodurrebbe l'assunzione appena smentita.
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

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from benchmarks.mtb_evidence.evaluation.cohort_split_audit import (  # noqa: E402
    DETECTOR_VERSION,
    SPLIT_LIKELIHOODS,
    SPLIT_REQUIRED,
    SPLIT_LIKELY,
    SPLIT_INSUFFICIENT_INFORMATION,
    screen_source,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_source_inventory import (  # noqa: E402
    write_csv,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")

COLUMNS = (
    "profile_unit_id",
    "canonical_source_id",
    "statement_count",
    "is_single_statement",
    "split_likelihood",
    "score",
    "signal_categories",
    "has_clinical_evidence",
    "has_preclinical_evidence",
    "source_availability",
    "review_priority",
    "text_basis",
    "negative_verdict_is_weak",
    "rationale",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    units = list(read_jsonl(args.corpus_dir / "source_profile_units.jsonl"))
    abstracts = {
        str(row["identifier_key"]): row
        for row in read_jsonl(args.curation_dir / "source_abstract_cache.jsonl")
    }
    already_audited = {
        str(row["profile_unit_id"]) for row in read_jsonl(args.audit_dir / "audit_scope.jsonl")
    }
    already_audited.add("PU-PMID-22277784-cohort-1")

    rows: list[dict[str, Any]] = []
    for unit in units:
        pmids = unit.get("pmids") or ()
        record = next((abstracts.get(f"pmid:{pmid}") for pmid in pmids if abstracts.get(f"pmid:{pmid}")), None)
        screened = screen_source(unit, record)
        screened["already_audited"] = screened["profile_unit_id"] in already_audited
        screened["screened_at"] = created_at
        rows.append(screened)

    rows.sort(key=lambda item: str(item["profile_unit_id"]))
    write_jsonl(args.audit_dir / "single_statement_split_screen.jsonl", rows)

    candidates = [
        row
        for row in rows
        if not row["already_audited"]
        and row["split_likelihood"] in (SPLIT_REQUIRED, SPLIT_LIKELY)
    ]
    candidates.sort(
        key=lambda item: (
            {SPLIT_REQUIRED: 0, SPLIT_LIKELY: 1}.get(item["split_likelihood"], 2),
            -int(item["score"]),
            str(item["profile_unit_id"]),
        )
    )
    write_csv(args.audit_dir / "single_statement_split_candidates.csv", candidates, COLUMNS)

    single = [row for row in rows if row["is_single_statement"]]
    single_candidates = [row for row in candidates if row["is_single_statement"]]
    by_likelihood = {key: 0 for key in SPLIT_LIKELIHOODS}
    for row in rows:
        by_likelihood[row["split_likelihood"]] = by_likelihood.get(row["split_likelihood"], 0) + 1

    residual_rate = round(len(candidates) / (len(rows) or 1), 4)

    summary = {
        "created_at": created_at,
        "detector_version": DETECTOR_VERSION,
        "sources_screened": len(rows),
        "single_statement_sources": len(single),
        "already_audited": sum(1 for row in rows if row["already_audited"]),
        "split_candidates": len(candidates),
        "single_statement_split_candidates": len(single_candidates),
        "by_split_likelihood": by_likelihood,
        "residual_split_risk_rate": residual_rate,
        "weak_negative_verdicts": sum(1 for row in rows if row.get("negative_verdict_is_weak")),
        "verdict_text_basis": {
            basis: sum(1 for row in rows if row.get("text_basis") == basis)
            for basis in ("full_text", "abstract", "none")
        },
        "note": (
            "screening leggero: nessuna unita' e' stata modificata e nessun profilo "
            "generato. I candidati sono fonti da esaminare, non fonti sbagliate."
        ),
    }
    write_json(args.audit_dir / "single_statement_screen_summary.json", summary)

    lines = [
        "# Screening del rischio di split non rilevato",
        "",
        f"- **Fonti esaminate:** {len(rows)} su 102",
        f"- **Fonti a statement singolo:** {len(single)}",
        f"- **Candidati allo split:** {len(candidates)}",
        f"- di cui a statement singolo: {len(single_candidates)}",
        f"- **Tasso di rischio residuo:** {residual_rate:.1%}",
        "",
        "## Perche' lo screening copre tutte le fonti",
        "",
        "La specifica lo chiedeva sulle fonti a statement singolo, che erano il rischio",
        "sospettato. Il caso PMID 22277784 ha mostrato che il rischio non e' legato al",
        "numero di statement: quella fonte ne aveva dieci ed era invisibile al rilevatore",
        "in produzione. Limitare lo screening alle single-statement avrebbe riprodotto",
        "l'assunzione appena smentita, quindi copre tutte e 102.",
        "",
        "## Distribuzione dei verdetti",
        "",
        "| Verdetto | Fonti |",
        "| --- | ---: |",
    ]
    for key in SPLIT_LIKELIHOODS:
        lines.append(f"| `{key}` | {by_likelihood.get(key, 0)} |")

    weak = sum(1 for row in rows if row.get("negative_verdict_is_weak"))
    lines += [
        "",
        "`insufficient_information` non e' un verdetto tranquillo. E' il bucket in cui",
        "PMID 22277784 era finito, e la priorita' di revisione per quelle fonti resta",
        "media, non bassa.",
        "",
        f"Anche `split_not_indicated` va letto con cautela: {weak} verdetti negativi sono",
        "stati formulati sul **solo abstract**, e sono quindi negativi deboli. Il campo",
        "`negative_verdict_is_weak` li marca uno per uno. Per trasformarli in negativi",
        "forti servirebbe il full text, che per queste fonti non e' stato recuperato.",
        "",
        "## Primi candidati",
        "",
        "| Fonte | Statement | Verdetto | Segnali | Priorita' |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for row in candidates[:15]:
        lines.append(
            f"| `{row['canonical_source_id']}` | {row['statement_count']} | "
            f"`{row['split_likelihood']}` | {', '.join(row['signal_categories'][:4])} | "
            f"{row['review_priority']} |"
        )

    lines += [
        "",
        "## Che cosa questo screening non e'",
        "",
        "Non e' una curation. Nessuna unita' e' stata modificata, nessun profilo",
        "generato, nessuna revisione prodotta. Un candidato e' una fonte **da guardare**,",
        "non una fonte sbagliata: i segnali dicono che la struttura potrebbe essere",
        "multipla, e solo la lettura puo' dirlo.",
        "",
    ]
    write_text(args.audit_dir / "SINGLE_STATEMENT_SCREEN_REPORT.md", "\n".join(lines) + "\n")

    print(f"fonti esaminate: {len(rows)} | a statement singolo: {len(single)}")
    print(f"candidati: {len(candidates)} | di cui single-statement: {len(single_candidates)}")
    print(f"verdetti: {by_likelihood}")
    print(f"rischio residuo: {residual_rate:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

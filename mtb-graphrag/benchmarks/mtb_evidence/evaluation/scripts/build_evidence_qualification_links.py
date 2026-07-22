"""Collega gli 8 SourceClinicalProfile revisionati ai 147 EvidenceStatement del pilota.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/\\
build_evidence_qualification_links.py \\
        --output benchmarks/mtb_evidence/v3/qualification

Offline: nessun grafo, nessuna rete, nessun modello.

**Il collegamento non e' una promozione.** Gli statement restano `origin: frozen_kg` e
`review_status: pending_verification`; i profili restano `reviewed_source_profile`.
Nessuno dei due viene modificato, e lo script lo verifica alla fine confrontando gli
hash prima e dopo.
"""

from __future__ import annotations

import argparse
import copy
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.pipeline.evidence.qualification import (  # noqa: E402
    AMBIGUOUS_MATCH,
    CONFLICTING_MATCH,
    EXACT_DOI,
    EXACT_NCT,
    EXACT_PMID,
    EXACT_SOURCE_MATCH,
    MULTI_SOURCE_MATCH,
    PROFILE_DIMENSIONS,
    build_links,
    build_views,
)
from backend.pipeline.evidence.repository import load_statements  # noqa: E402
from benchmarks.mtb_evidence.evaluation.source_profiles import (  # noqa: E402
    default_repository,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    fingerprint,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_STATEMENTS = Path(
    "benchmarks/mtb_evidence/evaluation/results/adapter_v1/evidence_statements.jsonl"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statements", type=Path, default=DEFAULT_STATEMENTS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _coverage(statements: Sequence[dict], views: Sequence[Any]) -> dict[str, Any]:
    """Copertura dei qualificatori prima e dopo la vista qualificata.

    'Prima' e' il frozen KG: le dimensioni cliniche sono tutte assenti, perche' lo
    schema del grafo non le modella. 'Dopo' e' cio' che i profili revisionati
    aggiungono. La differenza e' il contributo misurabile di questa fase.
    """
    before: dict[str, int] = {}
    for statement in statements:
        context = statement.get("clinical_context") or {}
        for dimension in PROFILE_DIMENSIONS:
            value = context.get(dimension)
            if value not in (None, "", [], {}, "unknown"):
                before[dimension] = before.get(dimension, 0) + 1

    after: dict[str, int] = {}
    for view in views:
        for dimension in view.qualified_dimensions:
            after[dimension] = after.get(dimension, 0) + 1

    total = max(len(statements), 1)
    return {
        "total_statements": len(statements),
        "before_frozen_kg": {d: before.get(d, 0) for d in PROFILE_DIMENSIONS},
        "after_qualified_view": {d: after.get(d, 0) for d in PROFILE_DIMENSIONS},
        "coverage_before": {d: round(before.get(d, 0) / total, 4) for d in PROFILE_DIMENSIONS},
        "coverage_after": {d: round(after.get(d, 0) / total, 4) for d in PROFILE_DIMENSIONS},
        "still_unknown": {
            d: total - after.get(d, 0) for d in PROFILE_DIMENSIONS
        },
    }


def _report(metrics: dict[str, Any], coverage: dict[str, Any]) -> str:
    lines = [
        "# Collegamento dei profili revisionati agli statement del pilota",
        "",
        f"- **Statement:** {metrics['statements_total']}",
        f"- **Profili revisionati:** {metrics['profiles_loaded']}",
        f"- **Statement con almeno un profilo:** {metrics['statements_with_at_least_one_profile']}",
        f"- **Link creati:** {metrics['links_total']}",
        "",
        "Il collegamento **non e' una promozione**: gli statement restano `frozen_kg` e",
        "`pending_verification`, i profili restano `reviewed_source_profile`, e nessuno",
        "dei due viene modificato.",
        "",
        "## Link per esito",
        "",
        "| Esito | Conteggio |",
        "| --- | ---: |",
        f"| `exact_source_match` | {metrics['exact_source_match']} |",
        f"| `multi_source_match` | {metrics['multi_source_links']} |",
        f"| `ambiguous_match` | {metrics['ambiguous_links']} |",
        f"| `conflicting_match` | {metrics['conflicting_links']} |",
        "",
        "## Link per metodo",
        "",
        "| Metodo | Conteggio |",
        "| --- | ---: |",
        f"| `exact_pmid` | {metrics['exact_pmid_links']} |",
        f"| `exact_doi` | {metrics['exact_doi_links']} |",
        f"| `exact_nct` | {metrics['exact_nct_links']} |",
        "",
        "Il matching e' **solo source-based**. Nessun confronto sul titolo entra in una",
        "decisione automatica: un titolo simile non e' la stessa fonte.",
        "",
        "## Precision e recall del linking",
        "",
        f"**{metrics['linking_precision']}** — non esiste un gold di collegamento",
        "indipendente contro cui calcolarle. Inventare un denominatore produrrebbe un",
        "numero senza referente. Il report riporta conteggi e copertura.",
        "",
        "## Copertura dei qualificatori",
        "",
        "| Dimensione | Prima (frozen KG) | Dopo (vista qualificata) | Ancora unknown |",
        "| --- | ---: | ---: | ---: |",
    ]
    for dimension in PROFILE_DIMENSIONS:
        lines.append(
            f"| `{dimension}` | {coverage['before_frozen_kg'][dimension]} "
            f"| {coverage['after_qualified_view'][dimension]} "
            f"| {coverage['still_unknown'][dimension]} |"
        )

    lines += [
        "",
        "La colonna *prima* e' a zero su ogni dimensione perche' lo schema del grafo V2",
        "non le modella: non e' un difetto dell'adapter ma il punto di partenza che i",
        "profili revisionati esistono per colmare.",
        "",
        "## Perche' un join per PMID non basta",
        "",
        "Un profilo descrive **lo studio**; uno statement descrive **una proposizione**",
        "estratta da quello studio. Uno studio contiene tipicamente piu' proposizioni, e",
        "un'analisi di sottogruppo o un braccio diverso non ereditano la linea di terapia",
        "del braccio principale.",
        "",
        "Prima di rendere una dimensione disponibile, il link verifica la coerenza su",
        "malattia e intervento. Se il profilo dichiara piu' interventi la coorte di",
        "riferimento non e' determinabile, lo stato e' `ambiguous_match`, e **nessun",
        "qualificatore ambiguo viene applicato**.",
        "",
        "## Stato di qualificazione delle viste",
        "",
        "| Stato | Conteggio |",
        "| --- | ---: |",
    ]
    for status, count in sorted(metrics["view_status_counts"].items()):
        lines.append(f"| `{status}` | {count} |")

    if metrics["unmatched_profiles"]:
        lines += [
            "",
            "## Profili non collegati",
            "",
            "Nessuno statement del pilota cita queste fonti:",
            "",
        ]
        lines += [f"- `{p}`" for p in metrics["unmatched_profiles"]]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = args.timestamp or datetime.now(timezone.utc).isoformat()

    repository = load_statements(args.statements)
    statements = repository.all()
    profiles = list(default_repository())

    # Impronte prima del collegamento: servono a dimostrare che nulla viene modificato.
    statements_before = fingerprint(statements)
    profiles_before = fingerprint([p.as_dict() for p in profiles])

    print(f"Statement: {len(statements)}")
    print(f"Profili revisionati: {len(profiles)}")

    links = build_links(statements, profiles, now=timestamp)
    views = build_views(statements, links)

    statements_after = fingerprint(repository.all())
    profiles_after = fingerprint([p.as_dict() for p in profiles])
    if statements_before != statements_after:
        raise SystemExit("ERRORE: gli statement sono stati modificati dal collegamento")
    if profiles_before != profiles_after:
        raise SystemExit("ERRORE: i profili sono stati modificati dal collegamento")

    linked_statements = {link.statement_id for link in links}
    linked_profiles = {link.source_profile_id for link in links}
    status_counts: dict[str, int] = {}
    for view in views:
        status_counts[view.qualification_status] = (
            status_counts.get(view.qualification_status, 0) + 1
        )

    metrics = {
        "generated_at_utc": timestamp,
        "statements_total": len(statements),
        "profiles_loaded": len(profiles),
        "links_total": len(links),
        "statements_with_source_match": len(linked_statements),
        "statements_with_at_least_one_profile": len(linked_statements),
        "unmatched_statements": len(statements) - len(linked_statements),
        "unmatched_profiles": sorted(
            p.source_id for p in profiles if p.source_id not in linked_profiles
        ),
        "exact_pmid_links": sum(1 for l in links if l.match_method == EXACT_PMID),
        "exact_doi_links": sum(1 for l in links if l.match_method == EXACT_DOI),
        "exact_nct_links": sum(1 for l in links if l.match_method == EXACT_NCT),
        "exact_source_match": sum(1 for l in links if l.match_status == EXACT_SOURCE_MATCH),
        "multi_source_links": sum(1 for l in links if l.match_status == MULTI_SOURCE_MATCH),
        "ambiguous_links": sum(1 for l in links if l.match_status == AMBIGUOUS_MATCH),
        "conflicting_links": sum(1 for l in links if l.match_status == CONFLICTING_MATCH),
        "view_status_counts": status_counts,
        "qualifier_addition_coverage": round(
            sum(len(v.qualified_dimensions) for v in views)
            / max(len(views) * len(PROFILE_DIMENSIONS), 1), 4
        ),
        "qualifier_provenance_completeness": round(
            sum(
                1
                for v in views
                for value in v.qualified_dimensions.values()
                if value.source_profile_id and value.qualification_link_id and value.value_origin
            ) / max(sum(len(v.qualified_dimensions) for v in views), 1), 4
        ),
        "linking_precision": "not_evaluated",
        "linking_recall": "not_evaluated",
        "linking_evaluation_note": (
            "Non esiste un gold di collegamento indipendente: precision e recall non "
            "sono calcolabili senza inventare un denominatore."
        ),
        "statements_unchanged": statements_before == statements_after,
        "profiles_unchanged": profiles_before == profiles_after,
        "no_promotion": all(
            s.get("review_status") == "pending_verification"
            and (s.get("provenance") or {}).get("origin") == "frozen_kg"
            for s in statements
        ),
    }
    coverage = _coverage(statements, views)

    output = args.output
    write_json(output / "repository_manifest.json", repository.manifest().as_dict())
    repository.to_jsonl(output / "evidence_statements.jsonl")
    write_jsonl(output / "qualification_links.jsonl", [l.as_dict() for l in links])
    write_jsonl(output / "qualified_evidence_views.jsonl", [v.as_dict() for v in views])
    write_jsonl(
        output / "ambiguous_links.jsonl",
        [l.as_dict() for l in links if l.match_status == AMBIGUOUS_MATCH],
    )
    write_jsonl(
        output / "conflicts.jsonl",
        [
            {"statement_id": v.statement_id, **dict(conflict)}
            for v in views for conflict in v.conflicts
        ],
    )
    write_json(output / "qualification_metrics.json", {**metrics, "coverage": coverage})
    write_text(output / "QUALIFICATION_REPORT.md", _report(metrics, coverage))

    print(f"Link creati: {len(links)}")
    print(f"  exact_source_match : {metrics['exact_source_match']}")
    print(f"  multi_source_match : {metrics['multi_source_links']}")
    print(f"  ambiguous_match    : {metrics['ambiguous_links']}")
    print(f"  conflicting_match  : {metrics['conflicting_links']}")
    print(f"Statement collegati: {metrics['statements_with_at_least_one_profile']}")
    print(f"Profili non collegati: {metrics['unmatched_profiles'] or 'nessuno'}")
    print(f"Stati delle viste: {status_counts}")
    print(f"Statement invariati: {metrics['statements_unchanged']} | "
          f"Profili invariati: {metrics['profiles_unchanged']} | "
          f"Nessuna promozione: {metrics['no_promotion']}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

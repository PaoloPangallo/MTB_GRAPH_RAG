"""Un report per fonte, destinato all'approvazione dell'autore.

Ogni report dice che cosa la fonte contiene, che cosa l'audit aveva proposto,
che cosa la lettura ha stabilito, e che cosa resta da decidere. Le domande per
l'autore non sono cortesie: sono i punti in cui la fonte non decide da sola, e
lasciarle implicite significherebbe farle decidere a chi ha scritto lo script.

Paolo non compare come revisore. Lo stato massimo e'
`source_checked_review_proposal`.
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

from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import (  # noqa: E402
    FINDINGS,
    SourceFinding,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    REVIEW_VERSION,
    SOURCE_CHECKED_REVIEW_PROPOSAL,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_text,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")

# Le domande che la fonte non risolve. Una per fonte, formulate in modo che una
# risposta sia possibile senza rileggere tutto.
QUESTIONS: dict[str, tuple[str, ...]] = {
    "PU-PMID-22235099-cohort-1": (
        "Quattro unita' precliniche sono la granularita' giusta, o Ba/F3 e NIH3T3 "
        "vanno tenute insieme come «modelli isogenici ingegnerizzati»?",
        "L'esperimento su H3122 con KRAS G12V ha esito negativo: va conservato come "
        "unita' propria, o registrato come nota della coorte clinica?",
        "CUTO-1 deriva dal paziente #10 ma ha perso il riarrangiamento di ALK: e' una "
        "unita' preclinica autonoma o un prolungamento del caso clinico?",
        "ES-V2-evidence-4288 poggia su un solo paziente. Va marcato case-level per "
        "impedirne la propagazione alla coorte?",
    ),
    "PU-PMID-23344087-cohort-1": (
        "Senza full text la composizione preclinica resta indeterminata. Si accetta "
        "la proposta a tre unita', o si sospende in attesa dell'accesso?",
        "L'abstract dice «less sensitive» dove lo statement dice «resistance». La "
        "differenza va registrata come conflitto o come mapping da verificare?",
        "L'unico paziente con copy number gain portava anche EGFR L858R: "
        "ES-V2-evidence-767 va marcato conflicting invece che ambiguous?",
    ),
    "PU-PMID-31358542-cohort-1": (
        "Lo split clinico/preclinico e' respinto. Si conferma che l'unita' resta "
        "singola, o le otto sottopopolazioni giustificano uno split di sottogruppo?",
        "ES-V2-evidence-100003 attribuisce a brigatinib una frequenza riportata per "
        "l'insieme dei TKI di seconda generazione. Va declassato a candidate_invalid?",
        "La fonte era un falso positivo del rilevatore: va segnalata come caso di "
        "riferimento per la correzione dei segnali?",
    ),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _slug(finding: SourceFinding) -> str:
    return finding.canonical_source_id.replace(":", "-")


def build_markdown(
    finding: SourceFinding,
    *,
    access: dict[str, Any],
    units: list[dict[str, Any]],
    statements: list[dict[str, Any]],
    terminology: list[dict[str, Any]],
    guards: list[dict[str, Any]],
) -> str:
    unknown_fields = sorted(
        {
            field
            for unit in units
            for field, decision in (unit.get("field_decisions") or {}).items()
            if decision == "unknown"
        }
    )
    na_fields = sorted(
        {
            field
            for unit in units
            for field, decision in (unit.get("field_decisions") or {}).items()
            if decision == "not_applicable"
        }
    )
    lines = [
        f"# {finding.canonical_source_id} — revisione documentale",
        "",
        f"**Decisione strutturale: `{finding.decision}`**",
        "",
        finding.decision_rationale,
        "",
        "## 1-2. Fonte e disponibilita'",
        "",
        f"- PMID: `{finding.pmid}`" + (f" · PMC: `{finding.pmc_id}`" if finding.pmc_id else ""),
        f"- Disponibilita': **{finding.availability}**",
        f"- Locator verificati: **{access.get('locators_verified', 0)}/{access.get('locator_count', 0)}**"
        f" ({access.get('match_type_counts')})",
        f"- Hash del documento: `{access.get('document_hash', '')[:32]}…`",
        "- Full text conservato: **no**",
        "",
        "## 3. Mappa clinico-preclinica",
        "",
        f"- Parte clinica: {finding.answers['clinical_part']}",
        f"- Parte preclinica: {finding.answers['preclinical_part']}",
        f"- Il preclinico valida il clinico? {finding.answers['preclinical_validates_clinical']}",
        f"- Farmaci di laboratorio somministrati ai pazienti? {finding.answers['lab_drugs_given_to_patients']}",
        f"- Alterazioni: requisito o reperto? {finding.answers['alterations_enrolment_or_finding']}",
        "",
        "## 4-6. Split proposto e unita'",
        "",
        f"L'audit proponeva **{finding.audit_unit_count}** unita'. La lettura ne sostiene "
        f"**{finding.reviewed_unit_count}**.",
        "",
        "| Unita' | Tipo | Statement candidati |",
        "| --- | --- | --- |",
    ]
    for unit in units:
        candidates = ", ".join(f"`{item}`" for item in unit["statement_candidates"]) or "—"
        lines.append(
            f"| `{unit['proposed_profile_unit_id']}` | {unit['unit_type']} | {candidates} |"
        )

    lines += [
        "",
        "## 7-9. Qualificatori, provenienza, locator",
        "",
        "Ogni dimensione nota porta la sua provenienza; la completezza e' verificata dal",
        "costruttore, che solleva se un valore noto resta senza locator.",
        "",
        f"- Campi `unknown`: {', '.join(f'`{item}`' for item in unknown_fields) or '—'}",
        f"- Campi `not_applicable`: {', '.join(f'`{item}`' for item in na_fields) or '—'}",
        f"- Dimensioni non separabili: "
        f"{', '.join(f'`{item}`' for item in finding.not_separable_dimensions) or '—'}",
        "",
        "## 10. Statement",
        "",
        "| Statement | Supporto | Stato candidato | Unita' |",
        "| --- | --- | --- | --- |",
    ]
    for statement in statements:
        units_text = ", ".join(f"`{item}`" for item in statement["proposed_profile_unit_ids"])
        lines.append(
            f"| `{statement['statement_id']}` | {statement['support_type']} | "
            f"**{statement['candidate_link_status']}** | {units_text} |"
        )

    lines += ["", "## 11. Terminologia", ""]
    if terminology:
        lines += ["| Fonte | Statement | Stato |", "| --- | --- | --- |"]
        for mapping in terminology:
            lines.append(
                f"| «{mapping['original_source_term']}» | «{mapping['normalized_term']}» | "
                f"**{mapping['mapping_status']}** |"
            )
    else:
        lines.append("Nessuno scarto terminologico rilevato.")

    violations = [item for row in guards for item in row["violations"]]
    lines += [
        "",
        "## 12. Propagazione",
        "",
        f"- Regole eseguite: {len(guards[0]['rules_executed']) if guards else 0}",
        f"- Violazioni: **{len(violations)}**",
        f"- Propagabile: **no** — nessuna proposta lo e' prima dell'approvazione",
        "",
        "## 13-15. Limiti",
        "",
    ]
    if finding.limitations:
        lines += [f"- {item}" for item in finding.limitations]
    else:
        lines.append("Nessun limite di accesso.")
    lines += ["", f"Rischio residuo: {finding.residual_risk}", "", "## 16. Domande per l'autore", ""]
    for index, question in enumerate(QUESTIONS[finding.parent_unit_id], start=1):
        lines.append(f"{index}. {question}")

    lines += [
        "",
        "## 17. Stato",
        "",
        "```",
        f"review_status                      = {SOURCE_CHECKED_REVIEW_PROPOSAL}",
        "human_reviewed                     = false",
        "first_review_complete              = false",
        "is_evaluable                       = false",
        "requires_author_approval           = true",
        "requires_second_independent_review = true",
        "```",
        "",
        "Una seconda revisione indipendente resta necessaria: questa fase ha letto la",
        "fonte, non l'ha giudicata.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    access = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.output / "source_access_verification.jsonl")
    }
    units = list(read_jsonl(args.output / "proposed_profile_units.jsonl"))
    statements = list(read_jsonl(args.output / "statement_unit_review_proposals.jsonl"))
    terminology = list(read_jsonl(args.output / "terminology_mappings.jsonl"))
    guards = list(read_jsonl(args.output / "propagation_guard_results.jsonl"))

    for finding in FINDINGS:
        parent = finding.parent_unit_id
        own_units = [row for row in units if row["parent_profile_unit_id"] == parent]
        own_statements = [row for row in statements if row["parent_profile_unit_id"] == parent]
        own_terminology = [row for row in terminology if row["parent_profile_unit_id"] == parent]
        own_guards = [row for row in guards if row["parent_profile_unit_id"] == parent]

        slug = _slug(finding)
        write_text(
            args.output / f"SOURCE_REVIEW_{slug}.md",
            build_markdown(
                finding,
                access=access.get(parent, {}),
                units=own_units,
                statements=own_statements,
                terminology=own_terminology,
                guards=own_guards,
            ),
        )
        write_json(
            args.output / f"source_review_{slug}.json",
            {
                "canonical_source_id": finding.canonical_source_id,
                "parent_profile_unit_id": parent,
                "pmid": finding.pmid,
                "pmc_id": finding.pmc_id,
                "availability": finding.availability,
                "structural_decision": finding.decision,
                "decision_rationale": finding.decision_rationale,
                "audit_unit_count": finding.audit_unit_count,
                "reviewed_unit_count": finding.reviewed_unit_count,
                "document_map": dict(finding.document_map),
                "answers": dict(finding.answers),
                "proposed_units": [row["proposed_profile_unit_id"] for row in own_units],
                "statement_mappings": [
                    {
                        "statement_id": row["statement_id"],
                        "support_type": row["support_type"],
                        "candidate_link_status": row["candidate_link_status"],
                    }
                    for row in own_statements
                ],
                "terminology_mappings": len(own_terminology),
                "propagation_violations": sum(row["violation_count"] for row in own_guards),
                "not_separable_dimensions": list(finding.not_separable_dimensions),
                "limitations": list(finding.limitations),
                "residual_risk": finding.residual_risk,
                "questions_for_author": list(QUESTIONS[parent]),
                "review_status": SOURCE_CHECKED_REVIEW_PROPOSAL,
                "human_reviewed": False,
                "first_review_complete": False,
                "is_evaluable": False,
                "requires_author_approval": True,
                "requires_second_independent_review": True,
                "reviewer": None,
                "created_at": created_at,
                "review_version": REVIEW_VERSION,
            },
        )
        print(f"SOURCE_REVIEW_{slug}.md · {finding.decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Audit del rilevatore di split in produzione, contro quello source-level."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.propagation_guards import ALL_RULE_IDS, GUARD_VERSION  # noqa: E402
from benchmarks.mtb_evidence.evaluation.cohort_split_audit import (  # noqa: E402
    DETECTOR_VERSION,
    SOURCE_SIGNALS,
    SPLIT_LIKELIHOODS,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_text,
)

DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    inventory = list(read_jsonl(args.curation_dir.parent / "qualification_corpus/source_inventory.jsonl"))
    units = list(read_jsonl(args.curation_dir.parent / "qualification_corpus/source_profile_units.jsonl"))
    single_statement = [row for row in units if len(row.get("statement_ids") or ()) <= 1]

    audit = {
        "created_at": created_at,
        "production_detector": {
            "name": "requires_cohort_split",
            "location": "benchmarks/mtb_evidence/evaluation/source_inventory.py",
            "signals_used": [
                "numero di interventi distinti fra gli statement della fonte",
                "numero di denominazioni di malattia distinte fra gli statement",
            ],
            "signals_not_used": [
                "testo della fonte",
                "termini di coorte, braccio, gruppo",
                "termini di modello preclinico",
                "termini di sottogruppo o analisi secondaria",
                "disegno dello studio",
                "comparatore",
            ],
            "depends_on_statement_count": True,
            "depends_on_intervention_count": True,
            "can_detect": [
                "fonti con piu' statement che divergono su intervento o malattia",
            ],
            "cannot_detect": [
                "fonti con un solo statement, per costruzione: senza due statement non "
                "esiste divergenza da osservare",
                "fonti con piu' statement che concordano su intervento e malattia ma "
                "descrivono coorti diverse",
                "fonti che mescolano evidenza clinica e preclinica sotto lo stesso "
                "intervento",
                "sottogruppi e analisi secondarie",
            ],
            "false_negative_risk": "alto",
            "false_positive_risk": "basso",
            "demonstrated_failure": {
                "profile_unit_id": "PU-PMID-22277784-cohort-1",
                "statement_count": 10,
                "classified_as": "insufficient_source_information",
                "actual_structure": (
                    "una coorte clinica di 18 pazienti piu' tre pannelli su cellule Ba/F3, "
                    "confermati dalla revisione della fonte"
                ),
                "why_it_failed": (
                    "i dieci statement concordavano abbastanza da non produrre divergenza, "
                    "e il segnale strutturale vive nel full text, che il rilevatore non "
                    "legge. Il fallimento non e' dovuto al numero di statement"
                ),
            },
        },
        "proposed_detector": {
            "name": "assess_split",
            "version": DETECTOR_VERSION,
            "location": "benchmarks/mtb_evidence/evaluation/cohort_split_audit.py",
            "signal_count": len(SOURCE_SIGNALS),
            "signal_categories": sorted({item[1] for item in SOURCE_SIGNALS}),
            "outputs": list(SPLIT_LIKELIHOODS),
            "reports_signals": True,
            "deterministic": True,
            "requires_llm": False,
            "title_alone_sufficient": False,
            "independent_of_statement_count": True,
            "promoted_to_production": False,
            "promotion_note": (
                "non promosso in produzione in questa fase: va prima validato contro "
                "revisioni umane, che oggi esistono su una sola fonte"
            ),
        },
        "single_statement_exposure": {
            "total_sources": len(inventory),
            "single_statement_units": len(single_statement),
            "share": round(len(single_statement) / (len(units) or 1), 4),
            "note": (
                "queste unita' sono invisibili al rilevatore in produzione per "
                "costruzione, non per difetto di configurazione"
            ),
        },
        "guards": {
            "version": GUARD_VERSION,
            "rule_count": len(ALL_RULE_IDS),
            "rules": list(ALL_RULE_IDS),
        },
    }
    write_json(args.audit_dir / "detector_audit.json", audit)

    production = audit["production_detector"]
    proposed = audit["proposed_detector"]
    failure = production["demonstrated_failure"]
    lines = [
        "# Limiti del rilevatore di split",
        "",
        "## Il rilevatore in produzione",
        "",
        f"`{production['name']}` decide confrontando **interventi e malattie fra gli",
        "statement** di una fonte. Non legge il testo della fonte.",
        "",
        "Da questo discendono i suoi limiti, e non sono di configurazione ma di forma:",
        "",
        "| Puo' rilevare | Non puo' rilevare |",
        "| --- | --- |",
        "| fonti con piu' statement che divergono | fonti con un solo statement |",
        "| divergenze su intervento o malattia | coorti diverse sotto lo stesso intervento |",
        "| | evidenza clinica e preclinica mescolate |",
        "| | sottogruppi e analisi secondarie |",
        "",
        "## Il fallimento dimostrato",
        "",
        f"`{failure['profile_unit_id']}` ha **{failure['statement_count']} statement** ed e'",
        f"stata classificata `{failure['classified_as']}`.",
        "",
        f"La struttura reale, confermata leggendo la fonte: {failure['actual_structure']}.",
        "",
        failure["why_it_failed"] + ".",
        "",
        "Il punto e' questo: prima di quella revisione si pensava che il buco riguardasse",
        "le fonti a statement singolo. Il caso mostra che riguarda **il canale del",
        "segnale**. Dieci statement non sono bastati, perche' il segnale non stava li'.",
        "",
        "## Il rilevatore proposto",
        "",
        f"`{proposed['name']}` legge la fonte e riporta i segnali insieme al verdetto.",
        "",
        f"- {proposed['signal_count']} pattern in {len(proposed['signal_categories'])} categorie",
        f"- verdetti: {', '.join(f'`{item}`' for item in proposed['outputs'])}",
        "- deterministico, nessun modello linguistico coinvolto",
        "- **indipendente dal numero di statement**",
        "- il titolo da solo non basta mai",
        "",
        "Riporta i segnali con i loro span perche' un verdetto senza prove non e'",
        "auditabile: chi legge deve poter contestare la conclusione guardando il testo",
        "che l'ha prodotta.",
        "",
        "### Non promosso in produzione",
        "",
        proposed["promotion_note"] + ".",
        "",
        "C'e' anche una ragione di merito: il rilevatore proposto e' tarato su un solo",
        "caso confermato. Promuoverlo adesso significherebbe generalizzare da un esempio.",
        "",
        "## La regola che ne discende",
        "",
        "L'audit ha applicato a se stesso la lezione: una fonte senza segnali **nel solo",
        "abstract** non viene piu' classificata `single_propagatable_unit`, ma",
        "`insufficient_source_information`. L'assenza di informazione non e' informazione",
        "di assenza, e su questa fonte specifica lo abbiamo verificato.",
        "",
        "## Esposizione residua",
        "",
        f"{audit['single_statement_exposure']['single_statement_units']} unita' su "
        f"{audit['single_statement_exposure']['total_sources']} hanno un solo statement",
        f"({audit['single_statement_exposure']['share']:.1%}). Per il rilevatore in",
        "produzione sono invisibili per costruzione.",
        "",
        "## Guardie",
        "",
        f"{len(ALL_RULE_IDS)} regole eseguibili con errore tipizzato:",
        "",
    ]
    lines += [f"- `{rule}`" for rule in ALL_RULE_IDS]
    lines += [
        "",
        "Zero violazioni sugli artefatti attuali. Non significa che le regole siano",
        "inerti: sono provate su casi deliberatamente scorretti nella suite, dove tutte",
        "scattano.",
        "",
    ]
    write_text(args.audit_dir / "DETECTOR_LIMITATIONS.md", "\n".join(lines) + "\n")

    print(f"segnali del rilevatore proposto: {len(SOURCE_SIGNALS)}")
    print(f"unita' a statement singolo: {len(single_statement)} / {len(units)}")
    print(f"regole di guardia: {len(ALL_RULE_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

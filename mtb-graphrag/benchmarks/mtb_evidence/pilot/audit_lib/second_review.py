"""Pacchetto per il secondo revisore indipendente.

Il revisore deve vedere domanda, contesto, claim provvisorie, fonti, record del grafo,
qualificatori e discrepanze - e nient'altro. In particolare non deve vedere la
decisione proposta dall'audit, l'output del GraphRAG o del planner, ne' alcuna
formulazione che indichi quale risposta accettare: un secondo giudizio contaminato
dal primo non e' un secondo giudizio.

Per questo il pacchetto si costruisce da gold e record grezzi, mai dal report, e le
discrepanze sono esposte in forma fattuale (quali valori differiscono) senza verdetto.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Mapping, Sequence

from .gold import GoldCase
from .normalize import norm_nct_set, norm_pmid_set
from .queries.base import CaseOutcome

DECISION_OPTIONS = ("accept", "accept_with_changes", "reject", "insufficient_information")

CASE_COLUMNS = (
    "case_id",
    "category",
    "question",
    "case_context",
    "gene",
    "variant",
    "disease",
    "required_context",
    "claim_count",
    "source_count",
    "graph_records_retrieved",
    "therapies_in_graph",
    "pmids_in_graph",
    "nct_ids_in_graph",
    "qualifiers_not_modelled_by_schema",
    "observed_differences",
    "reviewer_decision",
    "reviewer_notes",
)

CLAIM_COLUMNS = (
    "claim_id",
    "case_id",
    "subject",
    "relation",
    "object",
    "disease",
    "direction",
    "mandatory_qualifiers",
    "pmid",
    "nct_id",
    "graph_records_sharing_drug_and_pmid",
    "graph_record_ids",
    "graph_disease_values",
    "graph_direction_values",
    "graph_setting_labels",
    "dimensions_with_differing_values",
    "reviewer_decision",
    "reviewer_notes",
)

SOURCE_COLUMNS = (
    "source_record_id",
    "case_id",
    "source_type",
    "source_id",
    "title",
    "url_or_path",
    "role",
    "relevant_population_or_rule",
    "present_in_snapshot",
    "snapshot_lookup",
    "reviewer_decision",
    "reviewer_notes",
)


def _join(values: Sequence[Any]) -> str:
    return "; ".join(str(value) for value in values)


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> Path:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="\n")
    return path


def build_case_rows(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        case: GoldCase = entry["case"]
        outcome: CaseOutcome = entry["outcome"]
        comparison = entry["comparison"]
        differences = []
        if comparison["missing_therapies"]:
            differences.append(f"terapie del gold non presenti: {comparison['missing_therapies']}")
        if comparison["missing_pmids"]:
            differences.append(f"PMID del gold non presenti: {comparison['missing_pmids']}")
        if comparison["missing_nct_ids"]:
            differences.append(f"NCT del gold non presenti: {comparison['missing_nct_ids']}")
        if comparison["extra_therapies"]:
            differences.append(f"terapie nel grafo non nel gold: {comparison['extra_therapies']}")
        for conflict in comparison["conflicts"]:
            differences.append(
                f"{conflict['claim_id']}: {conflict['dimension']} gold "
                f"'{conflict['gold_value']}' / grafo '{conflict['graph_value']}'"
            )
        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "question": case.question,
                "case_context": case.case_context,
                "gene": case.gene,
                "variant": case.variant,
                "disease": case.disease,
                "required_context": case.required_context,
                "claim_count": len(case.claims),
                "source_count": len(case.sources),
                "graph_records_retrieved": len(outcome.graph_claims),
                "therapies_in_graph": _join(comparison["found_therapies"]),
                "pmids_in_graph": _join(comparison["found_pmids"]),
                "nct_ids_in_graph": _join(comparison["found_nct_ids"]),
                "qualifiers_not_modelled_by_schema": _join(comparison["not_modelled_by_schema"]),
                "observed_differences": _join(differences),
                "reviewer_decision": "",
                "reviewer_notes": "",
            }
        )
    return rows


def build_claim_rows(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        case: GoldCase = entry["case"]
        outcome: CaseOutcome = entry["outcome"]
        comparison = entry["comparison"]
        by_claim = {
            item["claim_id"]: item
            for group in (
                "structurally_matching_claims",
                "partially_matching_claims",
                "unmatched_claims",
            )
            for item in comparison[group]
        }
        for claim in case.claims:
            gold_pmids = set(norm_pmid_set(claim.pmid))
            anchored = [
                graph_claim
                for graph_claim in outcome.graph_claims
                if gold_pmids & set(graph_claim.pmids)
            ]
            match = by_claim.get(claim.claim_id, {})
            differing = [
                comparison_entry["dimension"]
                for comparison_entry in match.get("field_comparisons", [])
                if comparison_entry["status"] == "present_and_conflicts"
            ]
            rows.append(
                {
                    "claim_id": claim.claim_id,
                    "case_id": case.case_id,
                    "subject": claim.subject,
                    "relation": claim.relation,
                    "object": claim.object,
                    "disease": claim.disease,
                    "direction": claim.direction,
                    "mandatory_qualifiers": claim.mandatory_qualifiers,
                    "pmid": claim.pmid,
                    "nct_id": claim.nct_id,
                    "graph_records_sharing_drug_and_pmid": len(anchored),
                    "graph_record_ids": _join(sorted({c.record_id for c in anchored})),
                    "graph_disease_values": _join(sorted({c.disease for c in anchored if c.disease})),
                    "graph_direction_values": _join(
                        sorted({c.direction for c in anchored if c.direction})
                    ),
                    "graph_setting_labels": _join(
                        sorted({c.setting.label for c in anchored})
                    ),
                    "dimensions_with_differing_values": _join(differing),
                    "reviewer_decision": "",
                    "reviewer_notes": "",
                }
            )
    return rows


def build_source_rows(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        case: GoldCase = entry["case"]
        comparison = entry["comparison"]
        found_pmids = set(comparison["found_pmids"])
        found_ncts = set(comparison["found_nct_ids"])
        for source in case.sources:
            pmids = set(norm_pmid_set(source.source_id))
            ncts = set(norm_nct_set(source.source_id))
            if pmids:
                present = bool(pmids & found_pmids)
                lookup = f"nodo Publication con pmid {sorted(pmids)}"
            elif ncts:
                present = bool(ncts & found_ncts)
                lookup = f"nodo ClinicalTrial con nct_id {sorted(ncts)}"
            else:
                present = False
                lookup = "identificatore non risolvibile nel grafo (fonte non bibliografica)"
            rows.append(
                {
                    "source_record_id": source.source_record_id,
                    "case_id": case.case_id,
                    "source_type": source.source_type,
                    "source_id": source.source_id,
                    "title": source.title,
                    "url_or_path": source.url_or_path,
                    "role": source.role,
                    "relevant_population_or_rule": source.relevant_population_or_rule,
                    "present_in_snapshot": "yes" if present else "no",
                    "snapshot_lookup": lookup,
                    "reviewer_decision": "",
                    "reviewer_notes": "",
                }
            )
    return rows


INSTRUCTIONS = """# Istruzioni per la seconda revisione

## Che cosa ti viene chiesto

Le quattro annotazioni del pilota MTB-Evidence sono state prodotte una sola volta e
non sono ancora ground truth. Ti viene chiesto un giudizio **indipendente** su claim,
qualificatori e applicabilita'.

Indipendente vuol dire che questo pacchetto non contiene, deliberatamente, alcun
suggerimento su quale sia la risposta giusta: nessuna decisione gia' presa, nessun
output di sistemi automatici, nessun punteggio. Se ti sembra che manchi un'indicazione
su come decidere, e' voluto.

## Che cosa contiene il pacchetto

| File | Contenuto |
| --- | --- |
| `review_cases.csv` | domanda, contesto clinico e differenze osservate fra annotazione e snapshot |
| `review_claims.csv` | le claim provvisorie, con i valori corrispondenti trovati nel grafo |
| `review_sources.csv` | le fonti citate e se sono presenti nello snapshot |

Le colonne `graph_*` riportano i valori **osservati nel grafo**, non un giudizio.
`dimensions_with_differing_values` elenca le dimensioni su cui i due lati riportano
valori diversi, senza dire quale sia corretto.

## Come compilare

Per ogni riga compila `reviewer_decision` con uno di:

- `accept` - la claim e' corretta come scritta, qualificatori compresi;
- `accept_with_changes` - il nucleo regge ma qualcosa va corretto; scrivi cosa in `reviewer_notes`;
- `reject` - la claim non e' sostenibile;
- `insufficient_information` - non e' decidibile con quanto fornito; scrivi cosa servirebbe.

`reviewer_notes` e' libero ed e' la parte piu' utile: annota il motivo, non solo l'esito.

## Punti su cui prestare attenzione

- **Popolazione e linea.** Una claim vera in una popolazione gia' trattata puo' essere
  falsa in prima linea. Verifica che i qualificatori obbligatori siano tutti presenti.
- **Specificita' della malattia.** Un sottotipo e la sua categoria generale non sono
  intercambiabili.
- **Mutazione singola e composta.** Hanno implicazioni terapeutiche diverse e non vanno
  trattate insieme.
- **Assenza dallo snapshot.** `present_in_snapshot = no` significa che quella fonte non e'
  recuperabile da questo grafo. Non significa che la pubblicazione non esista, ne' che la
  claim sia falsa: e' un'informazione sulla copertura, e sta a te dire se cambia il giudizio.

## Dopo la compilazione

Restituisci i tre CSV compilati. I disaccordi con la prima annotazione verranno
riconciliati in una discussione esplicita, non risolti a maggioranza.
"""


def write_package(
    output_dir: Path, entries: Sequence[Mapping[str, Any]]
) -> dict[str, Path]:
    """Scrive i tre CSV e le istruzioni. Restituisce i path prodotti."""
    target = Path(output_dir)
    written = {
        "review_cases.csv": _write_csv(
            target / "review_cases.csv", CASE_COLUMNS, build_case_rows(entries)
        ),
        "review_claims.csv": _write_csv(
            target / "review_claims.csv", CLAIM_COLUMNS, build_claim_rows(entries)
        ),
        "review_sources.csv": _write_csv(
            target / "review_sources.csv", SOURCE_COLUMNS, build_source_rows(entries)
        ),
    }
    instructions = target / "reviewer_instructions.md"
    instructions.parent.mkdir(parents=True, exist_ok=True)
    instructions.write_text(INSTRUCTIONS, encoding="utf-8", newline="\n")
    written["reviewer_instructions.md"] = instructions
    return written

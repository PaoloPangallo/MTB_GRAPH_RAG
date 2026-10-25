"""Prosa della fase: politica, confronto fra modalita', readiness.

I report leggono le righe gia' ordinate dal generatore e non ricalcolano nulla: se
un numero comparisse qui e non negli artefatti, sarebbe un numero senza provenienza.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    AUDIT_ALL,
    CONTRACT_VERSION,
    ONTOLOGY_AWARE_WARNING,
    PHASE_VERSION,
    POLICY_MODES,
    RELATION_TYPES,
    STRICT_VERIFIED,
    EXACT_RELATIONS,
    MODE_TABLE,
)


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _yes(value: bool) -> str:
    return "si" if value else "no"


def policy_report(
    *,
    scope: Mapping[str, Any],
    definitions: Mapping[str, Any],
    coverage: Mapping[str, Any],
    flags: Mapping[str, Any],
) -> str:
    lines = [
        "# Politica gerarchica sulla disease",
        "",
        f"Fase `{PHASE_VERSION}` — contratto `{CONTRACT_VERSION}`.",
        "",
        "## Il problema",
        "",
        "Il matcher operativo riconosce gia' la gerarchia, ma la nomina in modo che",
        "non si puo' leggere. `explicit_parent` non dice di chi sia parent, e",
        "cross-disease, relazione irrisolta e disease mancante finiscono tutti in",
        "`unresolved`. Il risultato pratico e' corretto — nessuna di queste relazioni",
        "e' hard match — ma non e' spiegabile a chi legge un risultato.",
        "",
        "Questi due casi non sono lo stesso caso:",
        "",
        "```",
        "query  Cholangiocarcinoma                claim  Intrahepatic Cholangiocarcinoma",
        "  -> claim_is_child_of_query",
        "     l'evidenza vale solo per un sottotipo della query",
        "",
        "query  Intrahepatic Cholangiocarcinoma   claim  Cholangiocarcinoma",
        "  -> claim_is_parent_of_query",
        "     il risultato generale non e' separabile per il sottotipo chiesto",
        "```",
        "",
        "Nel primo caso generalizzare inventerebbe una copertura che la fonte non ha.",
        "Nel secondo specializzare inventerebbe una separabilita' che la fonte non",
        "dichiara. Sono errori diversi e vanno nominati diversamente.",
        "",
        "## Le relazioni",
        "",
    ]
    lines.extend(
        _table(
            ("relazione", "direzione", "exact", "regola sui dati congelati"),
            [
                (
                    f"`{item['relation_type']}`",
                    f"`{item['direction_rule']}`",
                    _yes(item["is_exact"]),
                    item["resolution_rule"],
                )
                for item in definitions["relations"]
            ],
        )
    )
    lines.extend(
        [
            "",
            "La direzione e' calcolata, non asserita: nasce dal confronto fra",
            "`_parent_key` e `_canonical_key`, non da una tabella scritta a mano.",
            "",
            "Nessuna relazione nuova viene creata. Le sole fonti sono `_SUBTYPE_OF` e",
            "`_SYNONYM_GROUPS` gia' congelati in `audit_lib/disease.py`, piu' il",
            "registro degli scope generici, che e' locale a questa fase e non viene",
            "applicato al matcher operativo.",
            "",
            "## Cio' che la politica vieta",
            "",
            "- Un risultato su iCCA non viene generalizzato a tutti i colangiocarcinomi.",
            "- Un risultato su tutti i colangiocarcinomi non viene specializzato su iCCA.",
            "- Un sibling non e' mai exact: `evidence:8173` resta audit-only per una",
            "  query iCCA, perche' il carcinoma colangiolocellulare non e' iCCA.",
            "- Uno scope generico non e' un alias della disease della query.",
            "- Un cross-disease non riceve punteggio positivo, neppure con biomarcatore",
            "  e intervento exact.",
            "- Una disease mancante non viene collassata in cross-disease: non sapere",
            "  non e' sapere che sono diverse.",
            "",
            "## Copertura sul corpus",
            "",
            f"Relazioni osservate sui claim dello shadow 1.2: "
            f"{len(coverage['relation_types_observed'])} tipi su {len(RELATION_TYPES)}.",
            "",
        ]
    )
    lines.extend(
        _table(
            ("relazione", "occorrenze"),
            [
                (f"`{name}`", str(count))
                for name, count in sorted(coverage["relation_types_observed"].items())
            ],
        )
    )
    missing = coverage["relation_types_without_corpus_occurrence"]
    if missing:
        lines.extend(
            [
                "",
                "Le relazioni senza occorrenze nel corpus non sono relazioni inutili:",
                "sono casi che il contratto deve saper dire anche quando i dati non li",
                "contengono. Sono coperte da probe espliciti in",
                "`regression_case_simulation.jsonl`:",
                "",
            ]
        )
        lines.extend(f"- `{name}`" for name in missing)
    lines.extend(
        [
            "",
            "## Perimetro",
            "",
            f"- gold usato: {_yes(scope['gold_used'])}",
            f"- metriche di retrieval calcolate: {_yes(scope['retrieval_metrics_used'])}",
            f"- gate implementato nel retriever operativo: "
            f"{_yes(scope['gate_implemented_in_operational_retriever'])}",
            f"- alias creati in questa fase: {scope['aliases_created']}",
            f"- relazioni create in questa fase: {scope['relations_created']}",
            f"- claim simulati: {scope['claims_simulated']}",
            f"- query congelate: {scope['frozen_query_count']}",
            f"- modalita': {scope['mode_count']}",
            f"- combinazioni prodotte: {scope['combination_count']}",
            "",
            f"Readiness del gate shadow: {_yes(flags['shadow_disease_gate_update_ready'])}. ",
            f"Promozione del corpus: {_yes(flags['corpus_promotion_ready'])}. ",
            f"Migrazione del retriever operativo: "
            f"{_yes(flags['operational_retriever_migration_ready'])}.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def modes_report(queries: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Strict, ontology-aware e audit",
        "",
        f"Contratto `{CONTRACT_VERSION}`.",
        "",
        "## Che cosa cambia, e che cosa no",
        "",
        "Il bucket primario e' **identico nelle tre modalita'**: exact, normalized",
        "exact e verified alias soltanto. Non esiste una modalita' broad, e non deve",
        "esistere: una modalita' che riportasse parent o child nel primario direbbe",
        "al lettore che quel claim risponde alla domanda posta, che e' esattamente",
        "cio' che la relazione nega.",
        "",
        "Cio' che cambia fra le modalita' e' che cosa si fa di una relazione che non",
        "e' identita', non se lo diventa.",
        "",
    ]
    for relation in RELATION_TYPES:
        row = [
            (
                f"`{mode}`",
                f"`{MODE_TABLE[relation][mode].bucket}`",
                _yes(MODE_TABLE[relation][mode].primary_candidate_eligible),
                _yes(MODE_TABLE[relation][mode].structural_score_eligible),
                _yes(MODE_TABLE[relation][mode].qualified_score_eligible),
            )
            for mode in POLICY_MODES
        ]
        lines.extend(["", f"### `{relation}`", ""])
        lines.extend(
            _table(("modalita'", "bucket", "primary", "score strutturale", "score qualificato"), row)
        )
    lines.extend(
        [
            "",
            "## Parent e child",
            "",
            "Restano visibili in tutte e tre le modalita', nel bucket",
            "`retained_with_warning`. Il claim e' pertinente e nasconderlo perderebbe",
            "informazione; presentarlo nel primario direbbe una cosa falsa. In",
            f"`{STRICT_VERIFIED}` non ricevono alcun punteggio. In",
            f"`{ONTOLOGY_AWARE_WARNING}` e in `{AUDIT_ALL}` possono essere ordinati",
            "fra loro: il punteggio qualificato serve a ordinare dentro il bucket",
            "warning, non a competere con il primario.",
            "",
            "## Il gate precede lo score",
            "",
            "Lo score strutturale e' riservato alle sole relazioni di identita'",
            f"({', '.join(sorted(EXACT_RELATIONS))}). Nessun segnale successivo —",
            "biomarcatore exact, intervento exact, qualita' della fonte,",
            "qualificazione, provenance, punteggio arbitrariamente elevato — puo'",
            "cambiare il bucket assegnato dal gate disease. Il caso `PROBE-SCORE-GATE`",
            "lo verifica iniettando tutti quei segnali insieme su una relazione child.",
            "",
            "## Per query e modalita'",
            "",
        ]
    )
    lines.extend(
        _table(
            ("query", "modalita'", "primary", "warning", "audit", "rejected"),
            [
                (
                    f"`{row['query_id']}`",
                    f"`{row['policy_mode']}`",
                    str(row["primary_candidate_count"]),
                    str(row["warning_count"]),
                    str(row["audit_only_count"]),
                    str(row["rejected_count"]),
                )
                for row in queries
            ],
        )
    )
    lines.extend(
        [
            "",
            "La colonna primary non cambia mai fra le tre righe di una stessa query.",
            "E' l'invariante che rende la modalita' una scelta di presentazione e non",
            "una scelta di verita'.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def readiness_report(
    *,
    flags: Mapping[str, Any],
    migration: Mapping[str, Any],
    integrity: Mapping[str, Any],
    regressions: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# Readiness della politica disease",
        "",
        f"Fase `{PHASE_VERSION}`.",
        "",
        "## Stato",
        "",
    ]
    lines.extend(
        _table(
            ("voce", "stato"),
            [
                (f"`{name}`", _yes(bool(value)))
                for name, value in sorted(flags.items())
                if isinstance(value, bool)
            ],
        )
    )
    lines.extend(
        [
            "",
            "Le tre voci finali restano chiuse per la stessa ragione di sempre: il",
            "contratto e' definito e simulato, non applicato. Promuovere il corpus o",
            "migrare il retriever sono decisioni successive, che questa fase prepara",
            "e non prende.",
            "",
            "## Audit del matcher operativo",
            "",
        ]
    )
    for category in migration["categories"]:
        lines.extend(
            [
                f"### {category['category']}",
                "",
                category["summary"],
                "",
            ]
        )
        lines.extend(
            _table(
                ("elemento", "oggi", "contratto", "riferimento"),
                [
                    (
                        f"`{item['item']}`",
                        item["current"],
                        item["proposed"],
                        f"`{item['reference']}`",
                    )
                    for item in category["findings"]
                ],
            )
        )
        lines.append("")
    lines.extend(
        [
            "## Regressioni",
            "",
        ]
    )
    lines.extend(
        _table(
            ("caso", "relazione", "exact", "atteso"),
            [
                (
                    f"`{row['case_id']}`",
                    f"`{row['relation_type']}`",
                    _yes(bool(row["is_exact_relation"])),
                    row["expectation"],
                )
                for row in regressions
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Integrita'",
            "",
            f"- parita' degli hash operativi: {_yes(integrity['operational_hash_parity'])}",
            f"- shadow repository modificati: "
            f"{_yes(integrity['shadow_repositories_modified'])}",
            f"- corpus operativo modificato: "
            f"{_yes(integrity['operational_corpus_modified'])}",
            f"- matcher operativo modificato: "
            f"{_yes(integrity['operational_disease_matcher_modified'])}",
            f"- riferimento di valutazione deserializzato: "
            f"{_yes(integrity['evaluation_reference_deserialized'])}",
            "",
            "## Prossimo passo",
            "",
            "Aggiornare il gate disease dello shadow repository usando questo",
            "contratto, mantenendo `strict_verified` come modalita' di default. La",
            "migrazione del matcher operativo resta chiusa fino a quando quel",
            "passaggio non e' stato verificato sullo shadow.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_reports(
    *,
    scope: Mapping[str, Any],
    definitions: Mapping[str, Any],
    coverage: Mapping[str, Any],
    flags: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any]],
    migration: Mapping[str, Any],
    integrity: Mapping[str, Any],
    regressions: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    return {
        "DISEASE_HIERARCHY_POLICY.md": policy_report(
            scope=scope, definitions=definitions, coverage=coverage, flags=flags
        ),
        "STRICT_VS_ONTOLOGY_AWARE_DISEASE_MATCHING.md": modes_report(queries),
        "DISEASE_POLICY_IMPLEMENTATION_READINESS.md": readiness_report(
            flags=flags,
            migration=migration,
            integrity=integrity,
            regressions=regressions,
        ),
    }


__all__ = ["build_reports", "modes_report", "policy_report", "readiness_report"]

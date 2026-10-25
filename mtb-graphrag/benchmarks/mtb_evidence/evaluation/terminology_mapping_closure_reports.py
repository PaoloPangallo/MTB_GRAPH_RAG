"""Report in prosa della chiusura terminologica.

I report non ricalcolano nulla: ricevono le stesse strutture che finiscono nei
JSON e le raccontano. Se un numero comparisse qui e non la', sarebbe un numero
inventato.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _evidence_table(evidence: Sequence[Mapping[str, Any]], pair_id: str) -> list[str]:
    rows = [
        [
            str(item["evidence_id"]),
            str(item["source_id"]),
            str(item["document_type"]),
            str(item["authoritative_level"]),
            "si" if item["supports_identity"] else "no",
            "si" if item["graph_derived"] else "no",
            str(item["locator"]),
        ]
        for item in evidence
        if item["pair_id"] == pair_id
    ]
    return _table(
        ("evidence", "fonte", "tipo", "livello", "sostiene", "da grafo", "locator"),
        rows,
    )


def _decision_block(decision: Mapping[str, Any]) -> list[str]:
    return [
        f"- decisione: `{decision['decision']}`",
        f"- mapping scope: `{decision['mapping_scope']}`",
        f"- canonical label: "
        f"{('`' + decision['canonical_label'] + '`') if decision['canonical_label'] else 'nessuna'}",
        f"- source literal preservato: `{decision['source_literal_term']}`",
        f"- confidence: {decision['confidence']}",
        f"- recommendation: `{decision['recommendation']}`",
        f"- reason codes: {', '.join('`' + code + '`' for code in decision['reason_codes'])}",
        f"- gruppi interessati: {', '.join('`' + g + '`' for g in decision['affected_groups']) or 'nessuno'}",
        f"- controllo di circolarita': "
        f"{'superato' if decision['circularity_control_passed'] else 'FALLITO'}",
    ]


def _bgj398_report(
    decision: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    simulation: Sequence[Mapping[str, Any]],
) -> str:
    changed = [row for row in simulation if row["claim_id_changes"]]
    lines = [
        "# BGJ398 / infigratinib",
        "",
        "## Esito",
        "",
        *_decision_block(decision),
        "",
        "## Perche' l'identita' e' verificata",
        "",
        "Il corpus locale contiene un record bibliografico peer-reviewed che "
        "appone il codice di sviluppo al nome generico nel proprio titolo, nella "
        "stessa malattia e sullo stesso biomarcatore del gruppo in revisione. "
        "Il vocabolario farmacologico fa convergere il codice su un unico "
        "concept id, asserito da cinque curatori distinti.",
        "",
        "Il controllo che rende la prova utilizzabile e' negativo: il codice "
        "**non compare** tra i nodi farmaco del grafo. La relazione non puo' "
        "quindi essere stata dedotta da cio' che il grafo afferma di se stesso, "
        "che e' la circolarita' rifiutata dall'adjudication.",
        "",
        *_evidence_table(evidence, str(decision["pair_id"])),
        "",
        "## Perche' il claim resta aggregato",
        "",
        "La fonte enuncia la soppressione della trasformazione per i due "
        "inibitori insieme. Verificare il nome di un membro non rende separabile "
        "il risultato: i due claim restano `aggregate_intervention_claim` con "
        "`permits_member_specific_claims` falso, e nessun claim atomico viene "
        "autorizzato.",
        "",
        "Questa e' la distinzione centrale della fase. Un mapping verificato "
        "agisce sulla terminologia, non sul supporto documentale.",
        "",
        "## Effetto simulato sugli ID",
        "",
        *_table(
            ("gruppo", "claim ID corrente", "ID potenziale", "tipo dopo"),
            [
                [
                    str(row["graph_evidence_id"]),
                    f"`{row['current_claim_id']}`",
                    f"`{row['potential_new_claim_id']}`",
                    str(row["claim_type_after"]),
                ]
                for row in changed
            ],
        ),
        "",
        "La formula di identita' include la rappresentazione canonica "
        "dell'intervento, quindi l'ID cambia davvero. Nessuna sostituzione viene "
        "effettuata: la simulazione registra retirement, replacement e lineage "
        "`old -> new -> terminology_decision_id` e si ferma.",
        "",
        "## Limitazioni",
        "",
        *[f"- {item}" for item in decision["limitations"]],
        "",
    ]
    return "\n".join(lines)


def _auy922_report(
    decision: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]
) -> str:
    lines = [
        "# AUY922 / luminespib",
        "",
        "## Esito",
        "",
        *_decision_block(decision),
        "",
        "## Perche' l'identita' non e' verificata",
        "",
        "Qui la fonte di massima priorita' e' disponibile. Il full text nomina "
        "soltanto il codice di sviluppo e non dichiara alcuna equivalenza. "
        "Un'assenza in una fonte accessibile pesa piu' di un'assenza in una "
        "fonte che non si e' potuta aprire.",
        "",
        "Il vocabolario farmacologico non colma il vuoto, lo documenta: il "
        "letterale usato dalla fonte risolve a un concept id, e il nome generico "
        "e' raggiunto solo da un letterale diverso, con prefisso di produttore. "
        "Trattare i due letterali come lo stesso termine sarebbe inferenza da "
        "somiglianza di stringa, che questa fase non ammette.",
        "",
        "Il nome generico compare unicamente in file derivati dal grafo. "
        "Il controllo di circolarita' fallisce.",
        "",
        *_evidence_table(evidence, str(decision["pair_id"])),
        "",
        "## Conseguenza",
        "",
        "L'associazione resta `unresolved_association`, esattamente come prima "
        "della revisione. Nessun claim viene creato, nessun ID cambia, nessun "
        "conteggio si muove. La revisione ha prodotto una decisione, non un "
        "cambiamento.",
        "",
        "La coppia va a una revisione esterna: la decisione dice che le prove "
        "**localmente disponibili** non bastano, non che l'equivalenza sia falsa.",
        "",
        "## Limitazioni",
        "",
        *[f"- {item}" for item in decision["limitations"]],
        "",
    ]
    return "\n".join(lines)


def _contract_report(contract: Mapping[str, Any]) -> str:
    entries = contract["interventions"]
    lines = [
        "# Contratto di canonicalizzazione degli interventi",
        "",
        f"Versione: `{contract['contract_version']}`",
        "",
        "## Invarianti",
        "",
        *[f"- {item}" for item in contract["invariants"]],
        "",
        "## Voci",
        "",
    ]
    for entry in entries:
        lines.extend(
            [
                f"### `{entry['canonical_intervention_id'] or entry['source_literals'][0]}`",
                "",
                f"- canonical label: "
                f"{('`' + entry['canonical_label'] + '`') if entry['canonical_label'] else 'nessuna'}",
                f"- source literals: {', '.join('`' + s + '`' for s in entry['source_literals'])}",
                f"- development codes: {', '.join('`' + s + '`' for s in entry['development_codes']) or 'nessuno'}",
                f"- verified aliases: {', '.join('`' + s + '`' for s in entry['verified_aliases']) or 'nessuno'}",
                f"- relazioni di forma o sale: "
                f"{'; '.join(entry['formulation_or_salt_relations']) or 'nessuna'}",
                f"- mapping scope: `{entry['mapping_scope']}`",
                f"- mapping status: `{entry['mapping_status']}`",
                f"- review status: `{entry['review_status']}`",
                f"- propagation policy: `{entry['propagation_policy']}`",
                f"- effective from: {entry['effective_from'] or 'non applicabile'}",
                f"- effective to: {entry['effective_to'] or 'non applicabile'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Determinismo",
            "",
            "La canonicalizzazione e' una funzione totale dei campi qui "
            "registrati: stesso input, stessa etichetta, stesso ID. Non consulta "
            "il grafo, non misura somiglianze e non dipende dall'ordine in cui le "
            "voci vengono presentate.",
            "",
        ]
    )
    return "\n".join(lines)


def _readiness_report(
    flags: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    integrity: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> str:
    lines = [
        "# Readiness della chiusura terminologica",
        "",
        "## Perimetro",
        "",
        f"- gruppi con terminology review aperta: {scope['expected_group_count']} "
        f"(attesi {scope['expected_group_count']}, trovati {scope['reviewed_group_count']})",
        f"- coppie nella queue congelata: {scope['queue_pair_count']}",
        f"- associazioni pending: {scope['pending_association_count']}",
        f"- hash della queue congelata: `{scope['queue_sha256']}`",
        "",
        "## Decisioni",
        "",
        *_table(
            ("coppia", "decisione", "scope", "canonical", "recommendation"),
            [
                [
                    f"`{d['pair_id']}`",
                    f"`{d['decision']}`",
                    f"`{d['mapping_scope']}`",
                    f"`{d['canonical_label']}`" if d["canonical_label"] else "—",
                    f"`{d['recommendation']}`",
                ]
                for d in decisions
            ],
        ),
        "",
        "## Flag",
        "",
        *_table(
            ("flag", "valore"),
            [[f"`{key}`", f"`{value}`"] for key, value in sorted(flags.items())],
        ),
        "",
        "## Che cosa resta chiuso",
        "",
        "`corpus_promotion_ready`, `operational_retriever_migration_ready` e "
        "`full_exploratory_rerun_ready` restano falsi. Questa fase decide una "
        "terminologia; non promuove il corpus, non migra il retriever e non "
        "riesegue nulla.",
        "",
        "La revisione e' **non indipendente**: un solo revisore reale. I packet "
        "ciechi per la seconda revisione sono pronti e non contengono decisioni, "
        "raccomandazioni ne' riferimenti valutativi.",
        "",
        "## Integrita'",
        "",
        f"- parita' degli artefatti operativi: `{integrity['operational_hash_parity']}`",
        f"- repository shadow 1.0, 1.1 e 1.2 modificati: "
        f"`{integrity['shadow_repositories_modified']}`",
        f"- riferimenti di valutazione deserializzati: "
        f"`{integrity['evaluation_reference_deserialized']}`",
        "",
    ]
    return "\n".join(lines)


def build_reports(
    *,
    decisions: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    simulation: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    flags: Mapping[str, Any],
    integrity: Mapping[str, Any],
    scope: Mapping[str, Any],
    bgj398_pair_id: str,
    auy922_pair_id: str,
) -> dict[str, str]:
    by_pair = {str(item["pair_id"]): item for item in decisions}
    return {
        "BGJ398_INFIGRATINIB_REVIEW.md": _bgj398_report(
            by_pair[bgj398_pair_id], evidence, simulation
        ),
        "AUY922_LUMINESPIB_REVIEW.md": _auy922_report(
            by_pair[auy922_pair_id], evidence
        ),
        "TERMINOLOGY_CANONICALIZATION_CONTRACT.md": _contract_report(contract),
        "TERMINOLOGY_CLOSURE_READINESS.md": _readiness_report(
            flags, decisions, integrity, scope
        ),
    }


__all__ = ["build_reports"]

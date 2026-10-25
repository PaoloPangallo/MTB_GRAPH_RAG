"""Report della fase 1.4, derivati dagli artefatti dati e non ricalcolati."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any


def _rows(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _flag(value: Any) -> str:
    if value is True:
        return "**true**"
    if value is False:
        return "false"
    return f"`{value}`"


def _fixes_report(artifacts: Mapping[str, str]) -> str:
    manifest = json.loads(artifacts["repository_v1_4_manifest.json"])
    findings = _rows(artifacts["post_fix_findings.jsonl"])
    matrix = _rows(artifacts["propagation_policy_matrix.jsonl"])
    ids = _rows(artifacts["claim_id_impact.jsonl"])
    plan = _rows(artifacts["qualification_link_plan_v1_4.jsonl"])
    compat = json.loads(artifacts["backward_compatibility_addendum.json"])
    counts = manifest["counts"]

    by_policy = Counter(row["propagation_policy"] for row in matrix)
    lines = [
        "# Correzioni richieste prima della promozione: repository 1.4",
        "",
        f"Repository: `{manifest['repository_schema']}`  ",
        f"Modello: `{manifest['model_schema']}`  ",
        f"Stato: `{manifest['migration_status']}`  ",
        f"Supera: `{manifest['supersedes']}`",
        "",
        "La 1.4 non aggiunge, non toglie e non riscrive nessuna proposizione.",
        "Applica quattro correzioni, ognuna legata a un finding dell'audit",
        "pre-promozione, e nessuna delle quali tocca una decisione gia' presa.",
        "",
        "## Conteggi",
        "",
        "| Voce | Derivato | Atteso |",
        "|---|---:|---:|",
    ]
    for key in sorted(manifest["expected_counts"]):
        lines.append(
            f"| `{key}` | {counts.get(key)} | {manifest['expected_counts'][key]} |"
        )
    lines += [
        "",
        f"Conteggi invariati rispetto alla 1.3: {_flag(manifest['counts_match_expected'])}.",
        "L'aggiunta della propagation policy non crea ne' elimina claim: e' un",
        "campo di governance, non una proposizione.",
        "",
        "## Propagation policy",
        "",
        "| Policy | Claim |",
        "|---|---:|",
    ]
    for policy, count in sorted(by_policy.items()):
        lines.append(f"| `{policy}` | {count} |")
    lines += [
        "",
        f"Claim con i tre campi obbligatori: **{len(matrix)}/{counts['active_claims_total']}**  ",
        f"Schema uniforme: {_flag(manifest['readiness']['propagation_policy_schema_uniform'])}  ",
        "Default impliciti in deserializzazione: "
        f"{_flag(manifest['propagation']['implicit_defaults_permitted'])}  ",
        "Record senza policy rifiutato: "
        f"{_flag(manifest['propagation']['record_without_policy_is_rejected'])}",
        "",
        "I sei claim che non dichiaravano la propria propagazione erano i tre",
        "aggregati e i tre regimi, cioe' esattamente quelli la cui propagazione va",
        "impedita. Il modello 1.1 aveva il campo su `AtomicInterventionClaim` e sui",
        "non terapeutici, e non sugli altri due tipi: l'asimmetria non si vede",
        "guardando i tipi uno per uno, e diventa un difetto quando i record",
        "vengono serializzati insieme.",
        "",
        "## Identita' dei claim",
        "",
        f"ID cambiati: **{sum(1 for row in ids if row['changed'])}**  ",
        f"ID verificati: **{len(ids)}**  ",
        f"Lineage richiesta: {_flag(any(row['lineage_required'] for row in ids))}",
        "",
        "I campi di propagazione non appartengono alla formula di identita' e non",
        "vi entrano ora. Il comportamento del gate non e' un campo del claim: un",
        "ID che cambiasse perche' una forma si comporta diversamente al retrieval",
        "direbbe che e' cambiata la proposizione, e non e' vero.",
        "",
        "## Link plan",
        "",
        f"Azioni: **{len(plan)}**  ",
        f"Schema: `{compat['link_plan']['schema_version']}`  ",
        f"Significato cambiato: {_flag(compat['link_plan']['meaning_changed'])}  ",
        f"Azioni eseguite: **{compat['link_plan']['actions_executed']}**",
        "",
        "Le tre forme precedenti sono mappate su un solo schema di sette campi. I",
        "campi legacy restano nell'artefatto della 1.3 e la mappa li registra,",
        "cosi' che la normalizzazione sia leggibile invece di dover essere dedotta",
        "dal codice che l'ha applicata.",
        "",
        "Un dettaglio merita di essere detto perche' e' una deviazione dallo",
        "schema richiesto: `source_unit_id` conserva il nome singolare e ha sempre",
        "valore di lista. Un'azione ne porta legittimamente due — prima linea e",
        "rechallenge dello stesso paziente — e sceglierne una sarebbe la perdita",
        "silenziosa che questa normalizzazione esiste per impedire.",
        "",
        "## Finding dell'audit pre-promozione",
        "",
        "| Finding | Prima | Dopo | Esito |",
        "|---|---|---|---|",
    ]
    for row in findings:
        lines.append(
            f"| `{row['finding_id']}` | `{row['severity_before']}` | "
            f"`{row['severity_now']}` | {row['outcome']} |"
        )
    lines += [
        "",
        "## Integrita'",
        "",
        f"Artefatti congelati invariati: {_flag(manifest['integrity']['all_frozen_artifacts_unchanged'])}  ",
        f"Parita' della query operativa: {_flag(manifest['integrity']['operational_query']['parity'])}  ",
        f"Record di gold letti: **{manifest['integrity']['gold']['gold_records_read']}**  ",
        f"Repository 1.3 modificato: {_flag(manifest['invariants']['shadow_1_3_modified'])}",
        "",
    ]
    return "\n".join(lines) + "\n"


def _formulation_report(artifacts: Mapping[str, str]) -> str:
    definitions = json.loads(artifacts["formulation_relation_definitions.json"])
    registry = _rows(artifacts["formulation_registry_snapshot.jsonl"])
    audit = _rows(artifacts["formulation_claim_audit.jsonl"])
    simulation = _rows(artifacts["formulation_gate_simulation.jsonl"])
    manifest = json.loads(artifacts["repository_v1_4_manifest.json"])

    salt_rows = [row for row in audit if row["form_kind"] == "salt"]
    leaving = [row for row in audit if row["retrieval_impact"] == "leaves_primary_bucket"]

    lines = [
        "# Contratto di matching fra active moiety, sale e formulazione",
        "",
        f"Contratto: `{definitions['contract_version']}`  ",
        f"Registro: `{definitions['registry_version']}`  ",
        f"Voci verificate: **{len(registry)}**",
        "",
        "## Il problema",
        "",
        "La 1.3 decide le relazioni di forma con una tupla di cinque suffissi.",
        "Chi finisce dentro la tupla diventa `normalized_atomic_intervention`,",
        "cioe' primario e con punteggio strutturale; chi resta fuori diventa",
        "`incompatible`, cioe' respinto come un farmaco senza alcuna relazione.",
        "",
        "| Coppia | Esito nella 1.3 | Fonte |",
        "|---|---|---|",
        "| `infigratinib hydrochloride` → `infigratinib` | primary | nessuna |",
        "| `infigratinib phosphate` → `infigratinib` | rejected | `EV-BGJ398-06` |",
        "| `alectinib` → `alectinib hydrochloride` | primary | nessuna |",
        "| `neratinib` → `neratinib maleate` | rejected | nessuna |",
        "",
        "L'unica coppia per cui una fonte autorevole esiste e' quella che la",
        "tabella respinge. Le altre tre non hanno nessuna fonte: la differenza fra",
        "loro e' soltanto quale suffisso qualcuno ha scritto nella tupla.",
        "",
        "## Le relazioni",
        "",
        "| Relazione | Bucket | Primary | Warning | Audit | Score strutturale |",
        "|---|---|---|---|---|---|",
    ]
    for row in definitions["relations"]:
        lines.append(
            f"| `{row['relation_type']}` | `{row['bucket']}` | "
            f"{_flag(row['primary_eligible'])} | {_flag(row['warning_eligible'])} | "
            f"{_flag(row['audit_eligible'])} | {_flag(row['structural_score_eligible'])} |"
        )
    lines += [
        "",
        "## La regola strict",
        "",
        f"> {definitions['exact_rule']}",
        "",
        "Non diventano mai exact:",
        "",
    ]
    for item in definitions["never_exact"]:
        lines.append(f"- {item}")
    lines += [
        "",
        f"Sottostringa puo' produrre exact: {_flag(definitions['substring_can_produce_exact'])}  ",
        f"Rimozione del suffisso puo' produrre exact: {_flag(definitions['suffix_stripping_can_produce_exact'])}  ",
        f"Distanza di edit puo' produrre exact: {_flag(definitions['edit_distance_can_produce_exact'])}",
        "",
        "I token di forma restano utili e cambiano ruolo. Dicono *che* due",
        "stringhe potrebbero parlare di forme diverse, ed e' quel sospetto — non",
        "una conclusione — che manda la coppia al registro. Se il registro tace,",
        "la relazione resta irrisolta.",
        "",
        "## Il registro",
        "",
        "| Forma | Moiety | Relazione | Fonte | Identificatori |",
        "|---|---|---|---|---|",
    ]
    for row in registry:
        lines.append(
            f"| `{row['form_label']}` | `{row['canonical_active_moiety']}` | "
            f"`{row['relation_type']}` | {row['authoritative_source']} "
            f"({row['evidence_id']}) | `{row['stable_identifier']}` contro "
            f"`{row['moiety_identifier']}` |"
        )
    lines += [
        "",
        "Il registro contiene una sola voce, e questo e' il fatto rilevante: la",
        "tabella dei suffissi ne trattava cinque come note. Una voce senza fonte",
        "non e' una relazione debole, e' una relazione che nessuno ha verificato,",
        "e il tipo `FormulationEntry` non permette di crearla.",
        "",
        "## Le due forme di infigratinib, decise separatamente",
        "",
    ]
    for pair in _reviewed_pairs(artifacts):
        lines += [
            f"### `{pair['form_label']}`",
            "",
            f"- moiety: `{pair['active_moiety']}`",
            f"- tipo di forma: `{pair['form_kind']}`",
            f"- origine della regola precedente: {pair['rule_origin']}",
            f"- fonte autorevole: {pair['authoritative_source'] or '**nessuna**'}",
            f"- relazione: `{pair['relation_status']}`",
            f"- prima: `{pair['previous_behaviour']}` → `{pair['previous_bucket']}`",
            f"- adesso: `{pair['new_decision']}` → `{pair['new_bucket']}`",
            f"- decisa per presenza nel grafo: {_flag(pair['decided_by_presence_in_graph'])}",
            f"- fusa con la moiety: {_flag(pair['fused_with_moiety'])}",
            "",
            pair["why"],
            "",
        ]

    lines += [
        "Le due forme ricevono esiti diversi perche' le prove disponibili sono",
        "diverse, non per simmetria e non perche' una delle due sia nel grafo.",
        "Nessuna delle due e' exact, e nessuna delle due e' fusa con la moiety.",
        "",
        "## Le forme nel repository",
        "",
        f"Claim con forma o codice: **{len(audit)}**  ",
        f"Claim in forma salina: **{len(salt_rows)}**  ",
        "Forme invisibili alla tabella dei suffissi: "
        f"**{len([row for row in salt_rows if not row['seen_by_current_suffix_table']])}**",
        "",
        "| Claim | Letterale | Token | Oggi | Domani | Impatto |",
        "|---|---|---|---|---|---|",
    ]
    for row in audit:
        tokens = ", ".join(f"`{token}`" for token in row["form_tokens"]) or "—"
        lines.append(
            f"| `{row['claim_id'][:16]}…` | `{row['source_literal']}` | {tokens} | "
            f"`{row['current_match_behavior']}` | `{row['proposed_match_behavior']}` | "
            f"{row['retrieval_impact']} |"
        )
    lines += [
        "",
        f"**{len(leaving)} claim** smettono di essere raggiunti nel bucket primario",
        "da una query sulla moiety nuda e diventano audit-only. Va detto senza",
        "attenuarlo: e' una perdita di copertura. Ma nessuna fonte lega quelle",
        "forme alla propria moiety, e la copertura che si perde e' quella che la",
        "tabella dei suffissi produceva senza averne il titolo. La voce resta",
        "aperta come informational per una revisione terminologica esterna.",
        "",
        "Nella direzione opposta, `neratinib maleate` smette di essere respinto",
        "come farmaco estraneo e diventa visibile in audit: `maleate` non era",
        "nella tupla, e la sua moiety veniva trattata come un'altra molecola.",
        "",
        "## Simulazione",
        "",
        "| Caso | Query | Claim | Relazione | Atteso |",
        "|---|---|---|---|---|",
    ]
    for row in simulation:
        lines.append(
            f"| `{row['case_id']}` | `{row['query_literal']}` | "
            f"`{row['claim_literal']}` | `{row['relation_type']}` | "
            f"{_flag(row['relation_as_expected'])} |"
        )
    lines += [
        "",
        "## Il gate",
        "",
        f"Gate: `{manifest['integrated_structural_gate']}`  ",
        f"Contratto di uscita: `{manifest['output_contract']}`",
        "",
        "La relazione di forma entra nella congiunzione **dopo** l'identita'",
        "dell'intervento e **prima** di direzione e punteggio. L'ordine non e'",
        "estetico: l'identita' risponde a \"e' lo stesso farmaco?\", la forma a",
        "\"e' la stessa forma di quel farmaco?\", e la seconda domanda ha senso solo",
        "dopo la prima.",
        "",
        "Un mismatch di forma non e' compensabile da disease exact, biomarcatore",
        "exact, provenance, qualita' della fonte o punteggio elevato.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _reviewed_pairs(artifacts: Mapping[str, str]) -> list[dict[str, Any]]:
    from benchmarks.mtb_evidence.evaluation.formulation_audit import reviewed_pairs

    return reviewed_pairs()


def _propagation_report(artifacts: Mapping[str, str]) -> str:
    manifest = json.loads(artifacts["repository_v1_4_manifest.json"])
    contract = manifest["propagation"]
    matrix = _rows(artifacts["propagation_policy_matrix.jsonl"])
    aggregates = _rows(artifacts["aggregate_propagation_audit.jsonl"])
    regimens = _rows(artifacts["regimen_propagation_audit.jsonl"])

    lines = [
        "# Contratto della propagation policy",
        "",
        f"Modello: `{contract['model_schema_version']}`  ",
        f"Contratto: `{contract['contract_version']}`",
        "",
        "## La regola",
        "",
        f"> {contract['rule']}",
        "",
        "| Voce | Valore |",
        "|---|---|",
        f"| campi obbligatori | {', '.join(f'`{f}`' for f in contract['required_fields'])} |",
        f"| valori ammessi | {', '.join(f'`{v}`' for v in contract['allowed_propagation_policies'])} |",
        f"| default in deserializzazione | {_flag(contract['deserialization_default'])} |",
        f"| default impliciti permessi | {_flag(contract['implicit_defaults_permitted'])} |",
        f"| record senza policy rifiutato | {_flag(contract['record_without_policy_is_rejected'])} |",
        "",
        "Obbligatorio significa due cose insieme, e la seconda e' quella che",
        "conta: la serializzazione li scrive sempre, e la deserializzazione",
        "**rifiuta** un record che non li porta. Un default in lettura riporterebbe",
        "il problema dov'era con in piu' l'illusione di averlo risolto: il campo",
        "comparirebbe nei record riletti, ma il suo valore sarebbe stato deciso dal",
        "parser invece che dalla revisione.",
        "",
        "## Aggregate claim",
        "",
        "| Claim | Membri | Policy | member_propagation | permits_member_specific |",
        "|---|---|---|---|---|",
    ]
    for row in aggregates:
        members = ", ".join(f"`{m}`" for m in row["members"])
        lines.append(
            f"| `{row['claim_id'][:16]}…` | {members} | `{row['propagation_policy']}` | "
            f"{_flag(row['member_propagation_allowed'])} | "
            f"{_flag(row['permits_member_specific_claims'])} |"
        )
    lines += [
        "",
        "Nessun membro eredita il risultato aggregato. E' la stessa inferenza che",
        "l'adjudication ha rifiutato su `evidence:275`, e lasciarla dedurre dal",
        "silenzio del record la avrebbe riaperta dal lato della serializzazione.",
        "",
        "## Regimen claim",
        "",
        "| Claim | Componenti | Policy | member_propagation | result_applies_to_combination |",
        "|---|---|---|---|---|",
    ]
    for row in regimens:
        components = ", ".join(f"`{c}`" for c in row["components"])
        lines.append(
            f"| `{row['claim_id'][:16]}…` | {components} | `{row['propagation_policy']}` | "
            f"{_flag(row['member_propagation_allowed'])} | "
            f"{_flag(row['result_applies_to_combination'])} |"
        )
    lines += [
        "",
        "Nessun componente eredita il risultato del regime. Un risultato di",
        "combinazione trasformato in monoterapia e' un'affermazione che la fonte",
        "non fa.",
        "",
        "## Atomic e diagnostic",
        "",
        f"Claim totali nella matrice: **{len(matrix)}**  ",
        "Atomic e diagnostic dichiaravano gia' `propagation_policy`; i due flag di",
        "valutabilita' esistevano soltanto sui non terapeutici e ora sono su tutti.",
        "Nessun valore documentale esistente e' stato cambiato: la fase dichiara",
        "cio' che mancava e non ridecide cio' che una revisione precedente aveva",
        "stabilito.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _readiness_report(artifacts: Mapping[str, str]) -> str:
    readiness = json.loads(artifacts["post_fix_readiness.json"])
    findings = _rows(artifacts["post_fix_findings.jsonl"])
    manifest = json.loads(artifacts["repository_v1_4_manifest.json"])

    lines = [
        "# Readiness del repository shadow 1.4",
        "",
        f"Repository: `{manifest['repository_schema']}`  ",
        f"Stato: `{manifest['migration_status']}`",
        "",
        "| Gate | Valore |",
        "|---|---|",
    ]
    for key in sorted(readiness):
        if key.endswith("_scope"):
            continue
        lines.append(f"| `{key}` | {_flag(readiness[key])} |")

    lines += [
        "",
        "## Finding",
        "",
        "| Finding | Prima | Dopo | Esito |",
        "|---|---|---|---|",
    ]
    for row in findings:
        lines.append(
            f"| `{row['finding_id']}` | `{row['severity_before']}` | "
            f"`{row['severity_now']}` | {row['outcome']} |"
        )

    lines += [
        "",
        "## Cosa significa `corpus_promotion_ready = true`",
        "",
        f"{readiness['corpus_promotion_ready_scope'].capitalize()}.",
        "",
        "Le due correzioni major richieste dall'audit sono applicate, e sono state",
        "applicate *prima* di scrivere il corpus, che era la ragione per cui la",
        "fase precedente teneva la porta chiusa. Nessun finding critical o major",
        "resta aperto.",
        "",
        "Cio' che questa readiness **non** dice: che il contenuto sia clinicamente",
        "valido. La revisione resta non indipendente, 131 claim su 148 non hanno",
        "mai avuto una revisione documentale, e il registro delle forme contiene",
        "una sola voce verificata.",
        "",
        "## Cosa resta falso, e perche'",
        "",
        "`operational_retriever_migration_ready` resta falso. Il retriever",
        "operativo non conosce i quattro bucket, non conosce le undici relazioni di",
        "malattia e non conosce le otto relazioni di forma. Promuovere il corpus",
        "non gliele insegna.",
        "",
        "`full_exploratory_rerun_ready` resta falso. Rieseguire l'esplorazione",
        "sopra un corpus non promosso misurerebbe una pipeline che non esiste.",
        "",
        "## La voce che resta aperta",
        "",
        "Dodici claim atomici in forma salina escono dal bucket primario per le",
        "query sulla moiety nuda. Non e' un difetto della 1.4: e' la conseguenza",
        "di non avere fonti per quelle forme. La voce e' registrata come",
        "informational e chiede una revisione terminologica esterna, che e' la",
        "stessa coda in cui `AUY922` aspetta dalla terminology closure.",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_reports(artifacts: Mapping[str, str]) -> dict[str, str]:
    return {
        "PRE_PROMOTION_REQUIRED_FIXES_1_4.md": _fixes_report(artifacts),
        "FORMULATION_MATCHING_CONTRACT.md": _formulation_report(artifacts),
        "PROPAGATION_POLICY_CONTRACT.md": _propagation_report(artifacts),
        "SHADOW_REPOSITORY_1_4_READINESS.md": _readiness_report(artifacts),
    }


__all__ = ["build_reports"]

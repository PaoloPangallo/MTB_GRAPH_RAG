"""Report leggibili dell'audit pre-promozione, derivati dagli artefatti dati.

I documenti non ricalcolano niente: leggono i JSON gia' emessi. Un report che
ricalcolasse potrebbe dire una cosa diversa dall'artefatto che dichiara di
descrivere, ed e' esattamente la divergenza che nessuno nota finche' non conta.
"""

from __future__ import annotations

import json
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


def _audit_report(artifacts: Mapping[str, str]) -> str:
    inventory = json.loads(artifacts["repository_inventory_audit.json"])
    identity = json.loads(artifacts["claim_id_recomputation.jsonl"].splitlines()[0])
    manifest = json.loads(artifacts["audit_manifest.json"])
    links = json.loads(artifacts["qualification_link_plan_audit.json"])
    views = json.loads(artifacts["qualified_view_plan_audit.json"])
    scope = json.loads(artifacts["audit_scope.json"])
    counts = inventory["audit_derived_counts"]
    totals = inventory["reconciliation_totals"]
    gate = _rows(artifacts["integrated_gate_audit.jsonl"])
    identity_rows = _rows(artifacts["claim_id_recomputation.jsonl"])
    provenance = _rows(artifacts["provenance_completeness_audit.jsonl"])

    blocked = sorted(
        {row["claim_id"] for row in provenance if row["promotion_blocking_absences"]}
    )
    lines = [
        "# Audit pre-promozione del repository shadow 1.3",
        "",
        f"Repository esaminato: `{scope['audited_repository']}`",
        f"Fase: `{scope['phase']}`  ",
        f"Promozione applicata: {_flag(scope['promotion_applied'])}  ",
        f"Piani eseguiti: {_flag(scope['plans_executed'])}  ",
        f"Gold usato: {_flag(scope['gold_used'])}",
        "",
        "L'audit e' read-only e deriva ogni conclusione dai file della 1.3. Il",
        "manifest della 1.3 e' stato caricato per essere confrontato con i dati,",
        "non per sostituirli: un manifest che si autodichiara coerente non e' una",
        "verifica.",
        "",
        "## Inventario",
        "",
        "| Voce | Derivato | Atteso |",
        "|---|---:|---:|",
    ]
    for key in sorted(inventory["expected_counts"]):
        lines.append(
            f"| `{key}` | {counts.get(key)} | {inventory['expected_counts'][key]} |"
        )
    lines += [
        "",
        f"Conteggi coerenti con l'atteso: {_flag(inventory['counts_match_expected'])}  ",
        f"Conteggi coerenti con il manifest: {_flag(inventory['counts_match_manifest'])}  ",
        f"Inventario coerente: {_flag(inventory['inventory_consistent'])}",
        "",
        "### Riconciliazione parent → claim",
        "",
        "| Voce | Totale |",
        "|---|---:|",
        f"| parent | {totals['parents']} |",
        f"| claim attivi | {totals['active_claims']} |",
        f"| claim ritirati | {totals['retired_claims']} |",
        f"| associazioni unsupported | {totals['unsupported_associations']} |",
        f"| associazioni unresolved | {totals['unresolved_associations']} |",
        f"| parent senza claim attivo | {totals['parents_without_active_claim']} |",
        "",
        "I tre parent senza claim sono "
        + ", ".join(f"`{item}`" for item in inventory["parents_without_claims_observed"])
        + ". Non sono una lacuna: nessuna fase ha materializzato un claim da",
        "quei record, e inventarne uno ora rifarebbe l'inferenza che le fasi",
        "precedenti hanno rifiutato.",
        "",
        "### Integrita' strutturale",
        "",
        "| Controllo | Esito |",
        "|---|---|",
    ]
    integrity = inventory["structural_integrity"]
    lines += [
        f"| nessun claim orfano | {_flag(integrity['no_orphan_claims'])} |",
        f"| nessun child verso parent inesistente | {_flag(not integrity['dangling_child_references'])} |",
        f"| ogni claim elencato dal proprio parent | {_flag(not integrity['claims_not_listed_by_their_parent'])} |",
        f"| nessun ritirato fra gli attivi | {_flag(not integrity['deprecated_claims_present_in_active_set'])} |",
        "",
        "## Identita'",
        "",
        f"Identita' ricalcolate: **{len(identity_rows)}**  ",
        f"ID non riproducibili: **{sum(1 for row in identity_rows if not row['matches'])}**  ",
        f"Collisioni: **{len(identity_rows) - len({row['declared_id'] for row in identity_rows})}**",
        "",
        "Ogni ID e' stato ricalcolato dai soli campi che la riga porta, senza",
        "chiedere al generatore di rifarlo. Due dettagli rendono la ricomputazione",
        "possibile a partire dal file, e chi promuovera' il corpus deve",
        "riprodurli: la source unit di identita' dei claim legacy e' il token",
        f"`{identity.get('identity_source_unit_id', '')[:34]}…`, non un elemento di",
        "`source_unit_ids`; e la forma canonica dell'intervento e' minuscola per i",
        "claim legacy e non per quelli adjudicati.",
        "",
        "## Provenance",
        "",
        "| Classe di assenza | Occorrenze |",
        "|---|---:|",
    ]
    prov_summary = {}
    for row in provenance:
        for item in row["missing_fields"]:
            key = f"{item['field']} → {item['classification']}"
            prov_summary[key] = prov_summary.get(key, 0) + 1
    for key in sorted(prov_summary):
        lines.append(f"| `{key}` | {prov_summary[key]} |")
    lines += [
        "",
        "Le due popolazioni della 1.3 hanno storie diverse e non vanno misurate",
        "con la stessa asticella. I 131 claim migrati dal legacy non hanno mai",
        "avuto una revisione documentale e lo dichiarano; chiedere loro un locator",
        "significherebbe chiedere di inventarlo. I 17 adjudicati lo portano.",
        "",
        "Resta una assenza che non e' spiegata da nessuna delle due storie: "
        + ", ".join(f"`{item}`" for item in blocked)
        + " non serializzano `propagation_policy`.",
        "",
        "## Piani",
        "",
        "| Piano | Azioni | Coerente |",
        "|---|---:|---|",
        f"| qualification link | {links['reconciliation']['total_actions']} | "
        f"{_flag(links['qualification_link_plan_consistent'])} |",
        f"| qualified view | {views['total_actions']} | "
        f"{_flag(views['qualified_view_plan_consistent'])} |",
        "",
        "Le 37 azioni di link si riconciliano cosi': "
        f"{links['reconciliation']['terminology_retire']} retire e "
        f"{links['reconciliation']['terminology_create']} create per la",
        f"terminologia, {links['reconciliation']['diagnostic_scope_retire']} retire e "
        f"{links['reconciliation']['diagnostic_scope_create']} create per il",
        f"restringimento diagnostico, {links['reconciliation']['carried_from_earlier_phases']} portate dalle fasi precedenti.",
        "Nessuna e' eseguita.",
        "",
        "Le 4 azioni di view sono 4 e non 2 per la ragione descritta",
        "nell'artefatto: due sono rigenerazioni diagnostiche vere, due sono",
        "**verifiche** che le view operative non nominino ne' il vecchio ne' il",
        "nuovo ID dei claim terminologici. Le view operative sono indicizzate per",
        "legacy statement e non per claim ID, quindi i due claim canonicalizzati",
        "non vi compaiono — e il modo di dimostrarlo e' contare le occorrenze,",
        "non assumerle.",
        "",
        "## Gate integrati",
        "",
        "| Caso | Bucket in strict_verified | Gate bloccanti |",
        "|---|---|---|",
    ]
    for row in gate:
        if row["policy_mode"] != "strict_verified":
            continue
        blocking = ", ".join(f"`{item}`" for item in row["blocking_gates"]) or "—"
        lines.append(f"| `{row['case_id']}` | `{row['final_bucket']}` | {blocking} |")
    lines += [
        "",
        f"Bypass osservati: **{manifest['invariants']['gate_bypasses']}**  ",
        "Flag di score sopravvissuti fuori dai bucket ordinabili: "
        f"**{manifest['invariants']['score_flags_leaked_outside_rankable_buckets']}**",
        "",
        "Il caso del punteggio arbitrariamente alto non sposta niente, ed e' il",
        "punto: il numero non entra in nessuna delle espressioni del gate.",
        "",
        "## Policy di default",
        "",
        "| Voce | Valore |",
        "|---|---|",
    ]
    policy = manifest["policy"]
    for key in (
        "declared_default_mode",
        "declared_default_mode_field",
        "strict_default_explicit",
        "behaviour_default_mode",
        "behaviour_rejects_unknown_mode",
        "unknown_mode_rejection_declared",
        "fallback_to_broader_mode_declared",
    ):
        lines.append(f"| `{key}` | {_flag(policy[key])} |")
    lines += [
        "",
        "Il default e' dichiarato machine-readably in `policy.default_mode` del",
        "manifest della 1.3, e il comportamento coincide. Cio' che non e'",
        "dichiarato e' che cosa accada a una modalita' sconosciuta: il codice la",
        "rifiuta, il manifest tace. Un consumatore che implementasse la pipeline",
        "dal solo manifest potrebbe scegliere un fallback invece di un errore, ed",
        "e' per questo che la dichiarazione entra fra le correzioni richieste alla",
        "promozione.",
        "",
        "## Integrita' della fase",
        "",
        f"Artefatti congelati invariati: {_flag(manifest['integrity']['all_frozen_artifacts_unchanged'])}  ",
        f"Parita' della query operativa: {_flag(manifest['integrity']['operational_query']['parity'])}  ",
        f"Record di gold letti: **{manifest['gold']['gold_records_read']}**",
        "",
        "Il bundle gold e' stato sottoposto a checksum senza essere",
        "deserializzato: dimostrare che non e' cambiato non richiede leggerne il",
        "contenuto, e la distinzione e' registrata nell'artefatto perche' non",
        "vada perduta.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _novelty_report(artifacts: Mapping[str, str]) -> str:
    summary = json.loads(artifacts["novelty_handling_summary.json"])
    rows = _rows(artifacts["novelty_handling_cases.jsonl"])
    terminology = [row for row in rows if row["domain"] == "terminology"]
    disease = [row for row in rows if row["domain"] == "disease"]

    lines = [
        "# Conservative novelty-handling diagnostics",
        "",
        "Queste misure **non sono accuratezza di generalizzazione** e non vanno",
        "chiamate cosi'. Non esiste nessun riferimento clinico: i casi sono",
        "sintetici, l'esito atteso e' derivato dalle sole tabelle congelate, e cio'",
        "che viene misurato e' se il sistema si astiene quando non sa — non se ha",
        "ragione.",
        "",
        "Non sono una misura di: "
        + ", ".join(f"*{item}*" for item in summary["not_a_measure_of"])
        + ".",
        "",
        "## Sintesi",
        "",
        "| Misura | Valore |",
        "|---|---:|",
        f"| unseen terms tested | {summary['unseen_terms_tested']} |",
        f"| exact promotions | {summary['exact_promotions']} |",
        f"| unresolved outcomes | {summary['unresolved_outcomes']} |",
        f"| rejected outcomes | {summary['rejected_outcomes']} |",
        f"| **false automatic merges** | **{summary['false_automatic_merges']}** |",
        f"| **gate bypasses observed** | **{summary['gate_bypasses_observed']}** |",
        f"| mapping creati da questa diagnostica | {summary['mappings_created_by_these_diagnostics']} |",
        f"| letterali di query riscritti | {summary['source_literal_preservation']['query_literals_rewritten']} |",
        "",
        "## Terminologia",
        "",
        "| Caso | Termine di query | Match type | Esito | Atteso |",
        "|---|---|---|---|---|",
    ]
    for row in sorted(terminology, key=lambda item: item["case_id"]):
        lines.append(
            f"| `{row['case_id']}` | `{row['query_term']}` | `{row['match_type']}` | "
            f"`{row['observed_outcome']}` | {_flag(row['outcome_as_expected'])} |"
        )
    lines += [
        "",
        "Nessun termine mai visto e' diventato exact per sottostringa, prefisso,",
        "distanza di edit, appartenenza alla stessa classe o conoscenza non",
        "registrata. `BGJ-398` e `NVP-AUY922` — le due variazioni grafiche che",
        "un lettore umano riconoscerebbe — restano respinte, e questo e' l'esito",
        "corretto: riconoscerle richiederebbe una regola che nessuno ha scritto.",
        "",
        "Un caso merita di essere letto per intero. `infigratinib hydrochloride`",
        "diventa `normalized_atomic_intervention`, quindi primario, perche'",
        "`hydrochloride` e' nella tabella dei suffissi salini. `infigratinib",
        "phosphate` resta `incompatible`, perche' `phosphate` non c'e'. La 1.3",
        "porta pero' nella propria terminology provenance il caveat opposto: il",
        "sale ha concept id proprio e non viene fuso nella moiety. Le due regole",
        "sono entrambe registrate, si contraddicono, e il repository contiene 12",
        "claim atomici con un intervento in forma salina — quindi la",
        "contraddizione e' raggiungibile, non teorica.",
        "",
        "## Malattia",
        "",
        "| Caso | Query | Claim scope | Relazione | Atteso |",
        "|---|---|---|---|---|",
    ]
    for row in sorted(disease, key=lambda item: item["case_id"]):
        query = f"`{row['query_disease']}`" if row["query_disease"] else "*(assente)*"
        claim = f"`{row['claim_disease']}`" if row["claim_disease"] else "*(assente)*"
        lines.append(
            f"| `{row['case_id']}` | {query} | {claim} | `{row['relation_type']}` | "
            f"{_flag(row['outcome_as_expected'])} |"
        )
    lines += [
        "",
        "Nessuna malattia mai vista e' diventata un alias verificato, e le due",
        "assenze restano distinte: `missing_query_disease` non e'",
        "`missing_claim_disease`, e nessuna delle due e' `cross_disease`. Un",
        "sottotipo non registrato non diventa un child: la gerarchia non viene",
        "estesa per somiglianza morfologica del nome.",
        "",
        "Resta una imprecisione di vocabolario, registrata come informational.",
        "Quando un solo termine e' ancorato al vocabolario congelato la relazione",
        "diventa `cross_disease`, cioe' *sono malattie diverse*, dove sarebbe piu'",
        "esatto dire che la relazione non e' registrata. In strict_verified",
        "l'esito e' identico — respinto — ma l'affermazione e' piu' forte di cio'",
        "che i dati autorizzano.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _promotion_report(artifacts: Mapping[str, str]) -> str:
    diff = json.loads(artifacts["promotion_diff_simulation.json"])
    compat = json.loads(artifacts["backward_compatibility_audit.json"])
    rollback = json.loads(artifacts["rollback_plan.json"])

    lines = [
        "# Simulazione della promozione e piano di rollback",
        "",
        "Niente di quanto segue e' stato eseguito. Il documento descrive che cosa",
        "*cambierebbe*, e la promozione resta una decisione separata.",
        "",
        "## Diff logico: corpus operativo → candidato promosso",
        "",
        f"Modalita': `{diff['promotion_mode']}`  ",
        f"Target: `{diff['promotion_target']}`  ",
        f"File operativi modificati: **{len(diff['operational_files_modified'])}**",
        "",
        "| Voce | Valore |",
        "|---|---:|",
        f"| file da creare | {len(diff['files_created'])} |",
        f"| file da sostituire | {len(diff['files_replaced'])} |",
        f"| righe da ritirare | {diff['rows_to_retire']} |",
        f"| righe da creare | {diff['rows_to_create']} |",
        f"| ID modificati | {diff['claim_ids_changed_count']} |",
        f"| qualification link toccati | {diff['qualification_links_modified']['total']} |",
        f"| statement del corpus operativo | {diff['operational_corpus_statements']} |",
        "",
        "La promozione **non sostituisce** il corpus v2: lo affianca. I file",
        "elencati sono nuovi, e nessuno di quelli operativi compare fra i",
        "sostituiti. E' la ragione per cui `operational_retriever_migration_ready`",
        "resta falso anche se il corpus fosse promosso: il retriever operativo non",
        "sa leggere il secondo corpus, e affiancarlo non lo insegna.",
        "",
        "### ID modificati",
        "",
        "| Vecchio | Nuovo | Record | Ragione |",
        "|---|---|---|---|",
    ]
    for row in diff["claim_ids_changed"]:
        lines.append(
            f"| `{row['old_claim_id']}` | `{row['new_claim_id']}` | "
            f"`{row['graph_evidence_id']}` | {row['reason']} |"
        )
    lines += ["", "### Incompatibilita' del retriever", "", "| Superficie | Dettaglio |", "|---|---|"]
    for row in diff["retriever_incompatibilities"]:
        lines.append(f"| {row['surface']} | {row['detail']} |")
    lines += ["", "### Incompatibilita' dello scoring", "", "| Superficie | Dettaglio |", "|---|---|"]
    for row in diff["scoring_incompatibilities"]:
        lines.append(f"| {row['surface']} | {row['detail']} |")
    lines += ["", "### Cambi di schema delle metriche e del renderer", "", "| Consumatore | Cambio |", "|---|---|"]
    for row in diff["metric_schema_changes"]:
        lines.append(f"| {row['consumer']} | {row['change']} |")
    for item in diff["report_renderer_changes"]:
        lines.append(f"| report renderer | {item} |")

    lines += [
        "",
        "## Compatibilita' all'indietro",
        "",
        "| Lookup | Risolvibile | Restituisce |",
        "|---|---|---|",
        f"| legacy statement ID | {_flag(compat['legacy_statement_id_lookup']['resolvable'])} | "
        f"{compat['legacy_statement_id_lookup']['returns']} |",
        f"| graph evidence ID | {_flag(compat['graph_evidence_id_lookup']['resolvable'])} | "
        f"{compat['graph_evidence_id_lookup']['returns']} |",
        f"| vecchio claim ID | {_flag(compat['old_claim_id_redirect']['resolvable'])} | "
        f"redirect verso il claim che lo sostituisce |",
        f"| claim ritirato | {_flag(compat['audit_of_retired_claims']['queryable'])} | "
        f"{compat['audit_of_retired_claims']['retrieval_path']} |",
        "",
        "### `intervention: string`",
        "",
        "Un client che si aspetta una stringa e riceve uno dei tre oggetti",
        "seguenti non deve essere accontentato appiattendolo. L'appiattimento e'",
        "l'errore che il modello tipizzato esiste per impedire, e rifarlo nel",
        "formato di uscita lo rifarebbe per intero.",
        "",
        "| Tipo | Claim | Riceve | Appiattirlo significherebbe |",
        "|---|---:|---|---|",
    ]
    for row in compat["intervention_contract"]["breaks"]:
        lines.append(
            f"| `{row['claim_type']}` | {row['claims_of_this_type']} | "
            f"{row['what_it_receives']} | {row['flattening_would']} |"
        )
    lines += [
        "",
        f"Appiattimento permesso dalla promozione: "
        f"{_flag(compat['intervention_contract']['flattening_permitted_by_promotion'])}",
        "",
        "## Rollback",
        "",
        f"Eseguito: {_flag(rollback['executed'])}  ",
        f"Passi: **{rollback['steps_total']}**  ",
        f"Claim deprecati conservati: {_flag(rollback['deprecated_claims_preserved'])}",
        "",
        "| # | Passo | Cosa | Modo di fallire che previene |",
        "|---:|---|---|---|",
    ]
    for row in rollback["steps"]:
        lines.append(
            f"| {row['step']} | {row['title']} | {row['what']} | "
            f"{row['failure_mode_prevented']} |"
        )
    lines += [
        "",
        "Il passo che di solito manca e' il primo. Uno snapshot preso dopo la",
        "scrittura non e' uno snapshot: e' una copia del nuovo stato, e il",
        "rollback che vi si appoggia ripristina esattamente cio' da cui si voleva",
        "tornare indietro.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _readiness_report(artifacts: Mapping[str, str]) -> str:
    decision = json.loads(artifacts["readiness_decision.json"])
    readiness = decision["readiness"]
    findings = _rows(artifacts["findings.jsonl"])

    lines = [
        "# Readiness alla promozione del repository 1.3",
        "",
        f"Decisione: **`{decision['decision']}`**",
        "",
        f"Ambito della decisione: {decision['decision_scope']}.",
        "",
        f"Readiness clinica dichiarata: {_flag(decision['clinical_readiness_declared'])}.",
        "Questa fase non ha gli elementi per dichiararla e non la dichiara: la",
        "revisione resta non indipendente e 131 claim su 148 non hanno mai avuto",
        "una revisione documentale.",
        "",
        "## Esiti",
        "",
        "| Voce | Valore |",
        "|---|---|",
    ]
    for key in sorted(readiness):
        if key.endswith("_scope"):
            continue
        lines.append(f"| `{key}` | {_flag(readiness[key])} |")

    lines += [
        "",
        "## Porte",
        "",
        "| Porta | Esito |",
        "|---|---|",
    ]
    for key in sorted(decision["gates"]):
        lines.append(f"| `{key}` | {_flag(decision['gates'][key])} |")

    lines += [
        "",
        "## Finding",
        "",
        "| Severita' | ID | Titolo |",
        "|---|---|---|",
    ]
    for row in findings:
        lines.append(f"| `{row['severity']}` | `{row['finding_id']}` | {row['title']} |")

    lines += [
        "",
        "### Correzioni richieste alla promozione",
        "",
    ]
    for item in decision["required_promotion_fixes"]:
        lines.append(f"- {item}")

    lines += [
        "",
        "## Perche' non `ready_for_prototype_promotion`",
        "",
        "Nessun finding critico e nessuna porta rossa: l'inventario e' coerente,",
        "gli ID si ricalcolano tutti, la lineage e' completa e reversibile, i gate",
        "reggono in tutte e tre le modalita', la diagnostica di novita' non mostra",
        "nessuna fusione automatica e nessun bypass. Cio' che manca non e' una",
        "verifica ma due decisioni, e sono decisioni che vanno prese *prima* di",
        "scrivere il corpus promosso, non dopo:",
        "",
        "1. i sei claim non atomici devono dichiarare la propria propagation",
        "   policy, perche' sono proprio quelli la cui propagazione va impedita;",
        "2. la forma salina deve essere normalizzazione oppure entita' distinta,",
        "   e oggi il repository dice entrambe le cose in due punti diversi.",
        "",
        "Nessuna delle due si risolve promuovendo e correggendo dopo: la prima",
        "cambierebbe il contenuto dei record, la seconda cambierebbe quali",
        "risultati entrano nel bucket primario.",
        "",
        "## Cosa resta falso, e perche'",
        "",
        "`operational_retriever_migration_ready` resta falso finche' il corpus non",
        "e' promosso: migrare un retriever verso un corpus che non esiste ancora",
        "non e' una decisione anticipabile.",
        "",
        "`full_exploratory_rerun_ready` resta falso. Rieseguire l'esplorazione",
        "sopra un corpus non promosso misurerebbe una pipeline che non esiste.",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_reports(artifacts: Mapping[str, str]) -> dict[str, str]:
    return {
        "PRE_PROMOTION_AUDIT_1_3.md": _audit_report(artifacts),
        "NOVELTY_HANDLING_DIAGNOSTICS.md": _novelty_report(artifacts),
        "PROMOTION_DIFF_AND_ROLLBACK.md": _promotion_report(artifacts),
        "PRE_PROMOTION_READINESS.md": _readiness_report(artifacts),
    }


__all__ = ["build_reports"]

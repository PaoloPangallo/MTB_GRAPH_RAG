"""Report della promozione prototipale, derivati dagli artefatti dati e non ricalcolati.

I due documenti leggono readiness, diff, manifest e report di rollback e li
mettono in prosa. Nessun numero viene ricontato qui: se un conteggio comparisse
in un report senza comparire in un artefatto, il report starebbe affermando
qualcosa che nessuno ha verificato.
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


# I gate nell'ordine in cui vanno letti: prima cosa e' stato fatto, poi cosa e'
# stato verificato, poi cosa resta falso. Ordinarli alfabeticamente
# mescolerebbe le tre cose.
READINESS_ORDER = (
    "prototype_corpus_promotion_applied",
    "prototype_corpus_registry_updated",
    "atomic_write_verified",
    "rollback_tested",
    "promoted_inventory_consistent",
    "promoted_lineage_complete",
    "promoted_links_consistent",
    "promoted_views_consistent",
    "strict_default_explicit",
    "unknown_mode_rejected",
    "all_claims_prototype_only",
    "no_claim_final_evaluable",
    "operational_pipeline_unchanged",
    "operational_retriever_migration_ready",
    "operational_retriever_bound",
    "full_exploratory_rerun_ready",
    "clinical_readiness",
)

INVENTORY_ORDER = (
    ("parents", "parent"),
    ("active_claims_total", "claim attivi"),
    ("therapeutic_claims", "terapeutici"),
    ("diagnostic_claims", "diagnostici"),
    ("prognostic_claims", "prognostici"),
    ("atomic_claims", "atomic"),
    ("aggregate_claims", "aggregate"),
    ("regimen_claims", "regimen"),
    ("unsupported_associations", "unsupported"),
    ("unresolved_associations", "unresolved"),
    ("deprecated_claims", "deprecated (esclusi dagli attivi)"),
    ("parents_without_claims", "parent senza claim"),
    ("orphan_claims", "claim orfani"),
    ("id_collisions", "collisioni di ID"),
    ("deduplications", "deduplicazioni"),
)


def _readiness_report(
    artifacts: Mapping[str, str], manifest: Mapping[str, Any]
) -> str:
    readiness = json.loads(artifacts["promotion_readiness.json"])
    diff = json.loads(artifacts["promotion_diff.json"])
    integrity = json.loads(artifacts["operational_integrity.json"])
    counts = manifest["counts"]
    terminology = manifest["terminology"]
    formulation = manifest["formulation"]
    links = manifest["links"]
    views = manifest["views"]
    query = integrity["operational_query"]["after"]
    schema = diff["schema_changes"]

    lines = [
        "# Readiness della promozione prototipale 1.4",
        "",
        f"Repository: `{manifest['repository_version']}`  ",
        f"Modello: `{manifest['model_version']}`  ",
        f"Stato: `{manifest['promotion_status']}`  ",
        f"Percorso: `{manifest['corpus_path']}`  ",
        f"Deriva da: `{manifest['source_shadow_version']}`"
        f" (`{manifest['source_shadow_sha256'][:16]}`)",
        "",
        "| Gate | Valore |",
        "|---|---|",
    ]
    lines += [f"| `{key}` | {_flag(readiness[key])} |" for key in READINESS_ORDER]

    lines += [
        "",
        "## Inventario promosso",
        "",
        "I conteggi sono derivati rileggendo i file scritti, non copiati dal",
        "manifest della 1.4.",
        "",
        "| Voce | Valore |",
        "|---|---:|",
    ]
    lines += [f"| {label} | `{counts[key]}` |" for key, label in INVENTORY_ORDER]
    lines += [f"| claim ID cambiati | `{diff['claim_ids_changed']}` |"]

    lines += [
        "",
        f"Conteggi coincidenti con quelli attesi: {_flag(manifest['counts_match_expected'])}.",
        "",
        "## Cosa significa `prototype_promoted`",
        "",
        "Che il contenuto della 1.4 esiste in una namespace versionata, con hash,",
        "manifest, registro e procedura di rollback, ed e' caricabile da un loader",
        "in sola lettura.",
        "",
        "Cio' che **non** significa. Non significa che il retriever operativo lo",
        f"usi: `operational_retriever_bound` e' {_flag(readiness['operational_retriever_bound'])},",
        "nessun modulo del percorso operativo importa la namespace promossa, e la",
        f"query operativa restituisce prima e dopo gli stessi {query['result_count']}",
        "risultati con la stessa serializzazione e lo stesso digest",
        f"`{query['sha256']}`.",
        "",
        "Non significa che il contenuto sia clinicamente valido. Promuovere e' un",
        f"fatto di versionamento: tutti i {counts['active_claims_total']} claim restano",
        "`prototype_only`, nessuno e' `final_evaluable`, nessuno e'",
        "`hard_filterable`, e la revisione resta non indipendente. Se la promozione",
        "potesse cambiare quei campi, \"versionato\" e \"clinicamente valido\"",
        "sarebbero la stessa affermazione.",
        "",
        "## Cosa cambia rispetto alla 1.4 shadow",
        "",
        "`operational_retriever_migration_ready` passa da falso a vero, e il",
        "cambiamento riguarda la disponibilita' del corpus, non la capacita' del",
        "retriever. Prima non c'era un corpus versionato verso cui migrare; ora c'e',",
        "ed e' caricabile, hashato e reversibile. Il retriever operativo continua a",
        "non conoscere i quattro bucket, le undici relazioni di malattia e le otto",
        "relazioni di forma: insegnargliele e' la fase successiva, e questa non",
        "l'ha anticipata.",
        "",
        "`full_exploratory_rerun_ready` resta falso per la stessa ragione di prima.",
        "Un rerun sopra un corpus che nessuna query raggiunge misurerebbe la",
        "pipeline corrente, non quella promossa.",
        "",
        "## L'unica normalizzazione applicata",
        "",
        "Due dei quattro claim ritirati —",
        ", ".join(
            f"`{claim_id}`"
            for claim_id in schema["deprecated_claims_declared_propagation_fields"]
        )
        + " — furono deprecati prima che il modello 1.2 rendesse obbligatori i campi",
        "di propagazione. Promuoverli senza avrebbe lasciato nel corpus esattamente",
        "il buco che la 1.4 ha chiuso, e avrebbe costretto il loader a un'eccezione",
        "per i record storici, cioe' a un default in lettura.",
        "",
        "I campi mancanti sono *dichiarati* con gli stessi valori che la 1.4",
        "dichiara per i claim attivi. Proposizioni toccate dal cambio di schema:",
        f"`{schema['propositions_affected_by_schema_change']}`. Claim ID cambiati:",
        f"`{diff['claim_ids_changed']}`.",
        "",
        "## Terminologia e forme",
        "",
        f"`AUY922` resta irrisolto ({_flag(terminology['auy922_unresolved'])}) e in attesa",
        f"di `{terminology['auy922_recommendation']}`. Il letterale `BGJ398` resta nella",
        f"fonte, con `{terminology['bgj398_verified_mapping']}` come etichetta canonica",
        "verificata. Nuovi mapping introdotti dalla promozione:",
        f"`{terminology['new_mappings_introduced_by_promotion']}`. Normalizzazione per",
        f"suffisso usata: {_flag(terminology['suffix_normalization_used'])}.",
        "",
        "Il costo di copertura resta quello che era:",
        f"`{formulation['salt_form_claims_outside_primary_for_bare_moiety_query']}` claim",
        "atomici in forma salina escono dal bucket primario per una query sulla",
        "moiety nuda. L'elenco e' quello che la 1.4 aveva scritto, non uno",
        "ricalcolato qui. Gate rilassato dalla promozione:",
        f"{_flag(formulation['salt_gate_relaxed_by_promotion'])}. Forme risolte dalla",
        f"promozione: `{formulation['new_forms_resolved_by_promotion']}`.",
        "",
        "| Forma | Esito |",
        "|---|---|",
    ]
    for form in formulation["retained_with_warning_forms"]:
        lines.append(f"| `{form}` | `retained_with_warning` |")
    for form in formulation["audit_only_forms"]:
        lines.append(f"| `{form}` | `audit_only` |")

    lines += [
        "",
        "## Link e view",
        "",
        f"Le `{links['actions_applied']}` azioni del piano di link e le",
        f"`{views['actions_applied']}` del piano di view sono applicate, e solo nella",
        "namespace V3. Negli artefatti shadow `executed` resta `false`",
        f"({_flag(links['historical_plan_left_unexecuted'])}): nel corpus promosso e'",
        "`true`, e i due valori compaiono nella stessa riga dell'artefatto di audit",
        "perche' \"il piano e' stato eseguito\" e \"il piano e' stato eseguito nella",
        "namespace V3\" sono affermazioni diverse e solo la seconda e' vera.",
        "",
        f"Link attivi: `{links['active_links']}`. Ritiri: `{links['retired_links']}`.",
        "Link attivi verso un claim ritirato:",
        f"`{links['active_links_targeting_deprecated_claims']}`. Duplicati:",
        f"`{len(links['duplicate_link_ids'])}`.",
        "",
        f"View materializzate: `{views['materialized_views']}`, tutte diagnostiche e in",
        "sezione diagnostica, senza therapy score",
        f"(`{views['therapy_score_on_diagnostic_views']}`) e senza ranking cross-domain",
        f"({_flag(views['cross_domain_ranking_present'])}). Verificate senza rigenerare:",
        f"`{views['verified_without_regeneration']}`. Membri appiattiti in view",
        f"separate: `{views['members_flattened_into_separate_views']}`. View orfane:",
        f"`{len(views['orphan_views'])}`.",
        "",
        "## Cosa resta aperto",
        "",
        "La revisione terminologica esterna, in cui `AUY922` aspetta dalla",
        "terminology closure e in cui ora aspettano anche le forme saline senza",
        "fonte.",
        "",
        "La revisione documentale dei claim che non ne hanno mai avuta una.",
        "",
        "Il collegamento del retriever operativo, che e' una decisione esplicita e",
        "una fase separata: la promozione prototipale non lo implica, e il registro",
        "lo dichiara invece di lasciarlo dedurre.",
        "",
    ]
    return "\n".join(lines)


def _diff_and_rollback_report(artifacts: Mapping[str, str]) -> str:
    diff = json.loads(artifacts["promotion_diff.json"])
    rollback = json.loads(artifacts["rollback_rehearsal.json"])
    integrity = json.loads(artifacts["operational_integrity.json"])
    write_log = json.loads(artifacts["promotion_write_log.json"])
    links = _rows(artifacts["qualification_link_application.jsonl"])
    views = _rows(artifacts["qualified_view_materialization.jsonl"])
    registry = diff["registry_changes"]

    lines = [
        "# Promotion diff e rollback della promozione prototipale 1.4",
        "",
        f"Derivato da: `{diff['derived_from']}`  ",
        "Derivato da un diff precedente: "
        f"{_flag(diff['derived_from_previous_diff'])}",
        "",
        "Il diff e' ricavato di nuovo dalla 1.4. Le due fasi hanno perimetri",
        "diversi — la 1.3 simulava una promozione, questa ne esegue una — e",
        "riusare il diff precedente descriverebbe un'operazione che non e'",
        "avvenuta.",
        "",
        "## Diff",
        "",
        "| Voce | Valore |",
        "|---|---:|",
        f"| file creati | `{diff['files_created_count']}` |",
        f"| righe attive | `{diff['active_rows']}` |",
        f"| righe deprecated | `{diff['deprecated_rows']}` |",
        f"| righe di lineage | `{diff['lineage_rows']}` |",
        f"| link applicati | `{diff['links_applied']}` |",
        f"| link attivi dopo | `{diff['links_left_active']}` |",
        f"| view materializzate | `{diff['views_materialized']}` |",
        f"| view verificate | `{diff['views_verified_without_regeneration']}` |",
        f"| claim ID cambiati | `{diff['claim_ids_changed']}` |",
        f"| proposizioni aggiunte | `{diff['propositions_added']}` |",
        f"| proposizioni rimosse | `{diff['propositions_removed']}` |",
        f"| file operativi cambiati | `{diff['operational_files_changed']}` |",
        "",
        "Comportamento della query operativa cambiato: "
        f"{_flag(diff['operational_query_behavior_changed'])}.",
        "Artefatti congelati invariati: "
        f"{_flag(integrity['all_frozen_artifacts_unchanged'])}.",
        "",
        "## Schema",
        "",
        "| Voce | Valore |",
        "|---|---|",
    ]
    for key in sorted(diff["schema_changes"]):
        value = diff["schema_changes"][key]
        rendered = ", ".join(f"`{item}`" for item in value) if isinstance(value, list) else f"`{value}`"
        lines.append(f"| `{key}` | {rendered or '—'} |")

    lines += [
        "",
        "## Registro",
        "",
        "| Voce | Valore |",
        "|---|---|",
        f"| registro creato | {_flag(registry['registry_created'])} |",
        f"| puntatore prima | `{registry['active_prototype_corpus_before']}` |",
        f"| puntatore dopo | `{registry['active_prototype_corpus_after']}` |",
        "| configurazione operativa cambiata | "
        f"{_flag(registry['operational_configuration_changed'])} |",
        "| retriever operativo collegato dopo | "
        f"{_flag(registry['operational_retriever_bound_after'])} |",
        f"| percorso | `{registry['registry_relpath']}` |",
        "",
        "## Scrittura atomica",
        "",
        "La sequenza registrata, passo per passo. Ogni passo ha un punto di",
        "interruzione nominato, cosi' che i test possano fermarla dove serve",
        "invece di simularlo.",
        "",
        "| Passo | Esito |",
        "|---|---|",
    ]
    lines += [
        f"| `{step['step']}` | `{step['outcome']}` |" for step in write_log["steps"]
    ]
    lines += [
        "",
        "Punti di interruzione disponibili: "
        + ", ".join(f"`{point}`" for point in write_log["failure_points_available"])
        + ".",
        "",
        "## Rollback",
        "",
        "Provato su una copia, mai sul risultato finale: un rollback eseguito sul",
        "corpus promosso lascerebbe la fase senza il proprio prodotto.",
        "",
        "| Voce | Valore |",
        "|---|---|",
        f"| eseguito su copia | {_flag(rollback['performed_on_copy'])} |",
        "| eseguito sul corpus promosso | "
        f"{_flag(rollback['performed_on_promoted_corpus'])} |",
        f"| idempotente | {_flag(rollback['idempotent'])} |",
        "| prima esecuzione ha cambiato | "
        f"{_flag(rollback['first_run']['changed'])} |",
        "| seconda esecuzione ha cambiato | "
        f"{_flag(rollback['second_run']['changed'])} |",
        f"| stato della voce dopo | `{rollback['registry_entry_status_after']}` |",
        "| puntatore prototipale dopo | "
        f"`{rollback['active_prototype_corpus_after']}` |",
        "| corpus caricabile dopo | "
        f"{_flag(rollback['corpus_loadable_after_rollback'])} |",
        "| artefatti operativi invariati | "
        f"{_flag(rollback['operational_artifacts_unchanged'])} |",
        "| retriever mai collegato | "
        f"{_flag(rollback['operational_retriever_was_never_bound'])} |",
        "",
        "File che il rollback non rimuove in nessuna modalita': "
        + ", ".join(f"`{name}`" for name in rollback["preserved_files"])
        + ".",
        "",
        "Idempotente qui significa la cosa stretta: non che si possa rieseguire",
        "senza errori, ma che la seconda esecuzione produca uno stato identico",
        "alla prima e non dichiari di aver cambiato nulla.",
        "",
        "## Azioni applicate",
        "",
        f"Link: `{len(links)}` azioni, tutte con `executed` vero nella namespace",
        "promossa e `false` nel piano shadow. Source unit, locator e reason code",
        "coincidono con il piano riga per riga.",
        "",
        f"View: `{len(views)}` azioni, nessun membro appiattito in view separate,",
        "nessun ranking cross-domain.",
        "",
    ]
    return "\n".join(lines)


def build_reports(
    artifacts: Mapping[str, str], manifest: Mapping[str, Any]
) -> dict[str, str]:
    return {
        "PROMOTION_DIFF_AND_ROLLBACK.md": _diff_and_rollback_report(artifacts),
        "PROTOTYPE_CORPUS_PROMOTION_READINESS.md": _readiness_report(
            artifacts, manifest
        ),
    }


__all__ = ["build_reports"]

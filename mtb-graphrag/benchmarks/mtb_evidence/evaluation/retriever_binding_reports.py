"""Report della fase di binding, derivati dagli artefatti e non ricalcolati.

I tre documenti leggono manifest, parita' e righe di regressione e li mettono in
prosa. Nessun numero viene ricontato qui: un conteggio che comparisse in un
report senza comparire in un artefatto starebbe affermando qualcosa che nessuno
ha misurato.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _flag(value: Any) -> str:
    if value is True:
        return "**true**"
    if value is False:
        return "false"
    return f"`{value}`"


READINESS_ORDER = (
    "promoted_corpus_loadable_by_v3_retriever",
    "v3_retriever_implemented",
    "backend_selection_explicit",
    "legacy_default_preserved",
    "unknown_backend_rejected",
    "unknown_policy_rejected",
    "strict_default_preserved",
    "four_bucket_output_implemented",
    "integrated_gates_applied",
    "provenance_complete",
    "dual_run_diagnostic_ready",
    "operational_pipeline_unchanged_for_legacy",
    "operational_retriever_bound_to_v3",
    "v3_prototype_endpoint_ready",
    "full_exploratory_rerun_ready",
    "clinical_readiness",
)


def architecture(manifest: Mapping[str, Any]) -> str:
    """Come il retriever V3 e' fatto, e cosa non fa."""
    contract = manifest["v3_retriever"]
    order = manifest["gate_execution_order"]
    scoring = manifest["scoring"]
    provenance = manifest["provenance_summary"]

    lines = [
        "# Architettura del retriever V3",
        "",
        f"Backend: `{contract['backend_name']}`  ",
        f"Versione: `{contract['backend_version']}`  ",
        f"Repository: `{contract['repository_version']}`  ",
        f"Gate: `{order['gate_version']}`  ",
        f"Corpus: `{manifest['corpus_hash']}`",
        "",
        "## Cosa il retriever non reimplementa",
        "",
        "Il retriever V3 e' un giro attorno a componenti gia' congelati. Il corpus",
        "lo apre il loader promosso, i gate li applica il gate integrato 1.1, i pesi",
        "vengono letti dalla configurazione operativa senza essere toccati. Cio' che",
        "questo modulo aggiunge e' quali oggetti entrano, come i bucket vengono",
        "composti e che cosa esce.",
        "",
        "| Componente | Origine |",
        "| --- | --- |",
        f"| Loader | `{contract['loader_module']}` |",
        f"| Gate | `{contract['gate_module']}` |",
        f"| Pesi | `{scoring['operational_weights_source']}` |",
        f"| Contratto di risultato | `{provenance['result_contract']}` |",
        "",
        "Il loader non viene duplicato su nessuno dei cinque assi che gia' copre:",
        "",
    ]
    for item in contract["loader_reused_not_duplicated"]:
        lines.append(f"- `{item}`")
    lines += [
        "",
        "## Ordine dei gate",
        "",
        "L'ordine non e' una descrizione a posteriori. I primi nove passi sono",
        "quelli che il gate integrato esegue, nella sequenza in cui li esegue, e un",
        "solo gate incompatibile annulla ogni eleggibilita' residua.",
        "",
        "| # | Passo |",
        "| --- | --- |",
    ]
    for row in order["order"]:
        lines.append(f"| {row['position']} | `{row['step']}` |")
    lines += [
        "",
        f"Lo scoring occupa la posizione {order['scoring_position']}: viene dopo la",
        "composizione dei bucket, e non prima. E' l'inversione rispetto al percorso",
        "operativo, dove un candidato entra nel ranking e poi viene penalizzato. Una",
        "penalita' e' un numero, e un numero puo' essere compensato da altri numeri;",
        "un bucket no.",
        "",
        "## I quattro bucket",
        "",
        "| Bucket | Reso di default | Punteggio |",
        "| --- | --- | --- |",
        "| `primary_ranked_results` | si | ranking consentito |",
        "| `retained_with_warning` | si | interno al bucket, dove il gate lo consente |",
        "| `audit_only_results` | no | registrato, mai usato per ranking clinico |",
        "| `rejected_by_native_constraints` | no | tutti gli score disabilitati |",
        "",
        "I candidati esclusi non vengono eliminati: restano nella struttura e sono",
        "recuperabili in modalita' di audit. Un retriever che li scartasse renderebbe",
        "la propria selettivita' non verificabile, perche' l'unica cosa osservabile",
        "sarebbe cio' che ha deciso di mostrare.",
        "",
        "## Oggetti candidati",
        "",
        "Entrano cinque famiglie, e nessuna delle ultime quattro puo' raggiungere il",
        "bucket primario: lo stato dell'oggetto lo impedisce prima di ogni match.",
        "",
    ]
    for kind in contract["candidate_object_kinds"]:
        lines.append(f"- `{kind}`")
    lines += [
        "",
        "## Cosa resta vero per costruzione",
        "",
        f"- il corpus non viene modificato dal retriever: {_flag(not contract['corpus_mutated_by_retriever'])}",
        f"- nessun ranking cross-domain: {_flag(not contract['cross_domain_ranking'])}",
        f"- il limite per bucket e' un limite di rendering: {_flag(contract['result_limit_is_a_rendering_limit'])}",
        f"- i pesi non sono stati ritarati: {_flag(not scoring['weights_retuned_in_this_phase'])}",
        f"- il gold non ha contribuito ai pesi: {_flag(not scoring['gold_used_for_weights'])}",
        "",
        "## Controlli d'avvio",
        "",
    ]
    for check in contract["startup_checks"]:
        lines.append(f"- `{check}`")
    lines += [
        "",
        "`operational_retriever_bound` puo' essere falso, ed e' il caso normale",
        "durante il binding test. Il campo dice che il percorso operativo non e'",
        "stato spostato sul corpus promosso, non che il corpus sia inutilizzabile.",
        "",
    ]
    return "\n".join(lines)


def binding(manifest: Mapping[str, Any], parity: Mapping[str, Any]) -> str:
    """Come la scelta del backend viene dichiarata, e cosa resta invariato."""
    selection = manifest["backend_selection"]
    pipeline = manifest["pipeline_binding"]
    probe = parity.get("isolation_probe", {})

    lines = [
        "# Legacy contro V3: il binding",
        "",
        f"Backend disponibili: {', '.join(f'`{name}`' for name in selection['available_backends'])}  ",
        f"Default: `{selection['default_retrieval_backend']}`  ",
        f"Policy di default: `{selection['default_policy_mode']}`  ",
        f"Policy ammesse: {', '.join(f'`{mode}`' for mode in selection['allowed_policy_modes'])}",
        "",
        "## La selezione e' una dichiarazione",
        "",
        "Non c'e' una regola che deduca il backend dalla forma della query, e non ce",
        "n'e' una che scelga il corpus piu' recente fra quelli presenti sul disco.",
        "Entrambe farebbero dipendere il comportamento della pipeline da cio' che e'",
        "stato promosso, e la promozione della 1.4 e' avvenuta con la promessa",
        "opposta.",
        "",
        "| Caso | Comportamento |",
        "| --- | --- |",
        f"| backend sconosciuto | `{selection['unknown_backend_behavior']}` |",
        f"| repository version sconosciuta | `{selection['unknown_repository_version_behavior']}` |",
        f"| policy mode sconosciuta | `{selection['unknown_policy_mode_behavior']}` |",
        f"| fallback silenzioso | {_flag(selection['silent_fallback_permitted'])} |",
        f"| selezione automatica del corpus piu' recente | {_flag(selection['automatic_latest_corpus_selection'])} |",
        "",
        "## Esiti misurati",
        "",
        "| Caso | Rifiutato |",
        "| --- | --- |",
    ]
    for row in manifest["selection_cases"]:
        lines.append(f"| `{row['case']}` | {_flag(row['rejected'])} |")
    lines += [
        "",
        "## Il risultato e' una union tipizzata",
        "",
        "La pipeline restituisce l'oggetto che il backend ha prodotto, non",
        "convertito. La conversione sarebbe la cosa piu' comoda e la piu' sbagliata:",
        "appiattire i claim V3 sugli statement legacy perderebbe i bucket, e",
        "appiattire gli statement legacy sui claim V3 affermerebbe una granularita'",
        "che il percorso operativo non ha.",
        "",
        f"- output legacy convertito in V3: {_flag(pipeline['legacy_output_converted_to_v3'])}",
        f"- V3 e' il default: {_flag(pipeline['v3_is_default'])}",
        f"- il binding vive nel corpus: {_flag(pipeline['binding_lives_in_corpus'])}",
        f"- backend costruito pigramente: {_flag(pipeline['backend_constructed_lazily'])}",
        "",
        "## Isolamento del percorso legacy",
        "",
        "La misura viene da un processo separato: dentro il processo che genera",
        "questi artefatti il modulo V3 e' gia' importato, e osservare `sys.modules`",
        "li' non direbbe nulla su cosa una run legacy carica per conto proprio.",
        "",
        f"- default osservato nel processo pulito: `{probe.get('default_backend', '')}`",
        f"- backend istanziati: {probe.get('instantiated_backends', [])}",
        f"- moduli del corpus V3 importati: {parity['v3_corpus_modules_imported_during_legacy_run']}",
        f"- invocazioni del loader promosso: {parity['v3_loader_invocations_during_legacy_run']}",
        f"- loader non inizializzato sotto legacy: {_flag(parity['v3_loader_not_initialized_under_legacy'])}",
        "",
        "## Parita' del percorso legacy",
        "",
        f"- serializzazione identica fra retriever diretto e adattatore: {_flag(parity['serialization_identical'])}",
        f"- query divergenti: {parity['mismatched_queries'] or 'nessuna'}",
        f"- default configurato: `{parity['configured_default_backend']}`",
        "",
        "Le query legacy che il contratto d'ingresso rifiuta restano registrate come",
        "rifiutate su entrambi i lati: un rifiuto identico e' anch'esso una parita',",
        "e nasconderlo renderebbe il confronto piu' pulito di quanto sia.",
        "",
    ]
    return "\n".join(lines)


def readiness(
    manifest: Mapping[str, Any],
    regression: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[Mapping[str, Any]],
) -> str:
    """Cosa e' pronto per il rerun esplorativo, e cosa esplicitamente non lo e'."""
    flags = manifest["readiness"]
    diagnostic = manifest.get("diagnostic", {})
    del diagnostic

    lines = [
        "# Readiness del rerun esplorativo",
        "",
        f"Fase: `{manifest['phase']}`  ",
        f"Repository: `{manifest['v3_retriever']['repository_version']}`  ",
        f"Corpus: `{manifest['corpus_hash']}`  ",
        f"Query di regressione: {manifest['queries']}",
        "",
        "| Flag | Valore |",
        "| --- | --- |",
    ]
    for name in READINESS_ORDER:
        lines.append(f"| `{name}` | {_flag(flags[name])} |")
    lines += [
        "",
        "## Perche' `operational_retriever_bound_to_v3` resta falso",
        "",
        "Il flag ha due letture, e questa fase ne soddisfa una sola. Il retriever V3",
        "e' **selezionabile**: una configurazione esplicita lo raggiunge, lo esegue e",
        "ne ottiene i quattro bucket. Il retriever V3 non e' **collegato**: il default",
        "resta `legacy`, il percorso operativo non lo attraversa, e nessun endpoint",
        "esistente ha cambiato contratto. Dichiarare vero il flag qui significherebbe",
        "affermare la seconda lettura sulla base della prima.",
        "",
        "## Perche' `clinical_readiness` resta falso",
        "",
        "Nulla in questa fase e' stato confrontato con il gold. Il dual-run misura",
        "*dove* i due backend divergono, non *quale dei due ha ragione*: e' una",
        "preparazione del rerun, non una sua valutazione. Tutti i claim del corpus",
        "restano `prototype_only`, con `hard_filterable` e `final_evaluable` falsi, e",
        "una idoneita' clinica non si deduce da un retriever che funziona.",
        "",
        "## Regressioni",
        "",
        "| Query | primary | warning | audit | rejected | deterministica |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in regression:
        counts = row["bucket_counts"]
        lines.append(
            f"| `{row['query_id']}` | {counts['primary_ranked_results']} | "
            f"{counts['retained_with_warning']} | {counts['audit_only_results']} | "
            f"{counts['rejected_by_native_constraints']} | {_flag(row['deterministic'])} |"
        )
    lines += [
        "",
        "## Dual-run",
        "",
        "| Query | overlap | solo legacy | solo V3 | errori |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in diagnostics:
        lines.append(
            f"| `{row['query_id']}` | {len(row['graph_evidence_overlap'])} | "
            f"{len(row['legacy_only_graph_evidence'])} | "
            f"{len(row['v3_only_graph_evidence'])} | "
            f"{sorted(row['errors']) or 'nessuno'} |"
        )
    lines += [
        "",
        "L'overlap si misura sul `GraphEvidenceRecord` e non sul numero di risultati.",
        "Un `EvidenceStatement` legacy e un claim V3 non stanno in corrispondenza uno",
        "a uno — `evidence:11240` ha due claim attivi da un solo parent — e",
        "confrontare i due conteggi darebbe la differenza fra due misure di cose",
        "diverse.",
        "",
        "## Prossimo passo",
        "",
        "Il rerun esplorativo comparativo sull'intero insieme di query, con il",
        "backend V3 selezionato esplicitamente e il legacy ancora default. Le",
        "metriche contro il gold restano fuori da questa fase e dalla successiva",
        "finche' il confronto non e' stato prima descritto senza giudicarlo.",
        "",
    ]
    return "\n".join(lines)


__all__ = ["READINESS_ORDER", "architecture", "binding", "readiness"]

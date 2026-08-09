# Confronto forense: vecchio percorso LIVE contro runtime canonico

Prodotto durante la rimozione della selezione di modalità dal runtime. La
domanda a cui questi artefatti rispondono è una sola:

> il routing è cambiato e il risultato no?

Rimuovere un'alternativa di instradamento non deve spostare di un identificatore
ciò che la pipeline produce. L'unico modo di affermarlo è eseguire gli stessi
ingressi sui due commit e confrontare gli artefatti, che è ciò che è stato
fatto.

## File

| File | Cosa contiene |
|---|---|
| `old_legacy_live.json` | osservazione prodotta su `f52bbf5`, dove `run_case` ha ancora `execution_mode` e il percorso si chiama LIVE |
| `new_canonical.json` | stessa osservazione sul runtime canonico |
| `diff_report.json` | confronto dei due |

## Come sono stati prodotti

    # sul runtime canonico
    python scripts/compare_canonical_vs_legacy_live.py --out evaluation/canonical_runtime_forensics/new_canonical.json

    # su un worktree temporaneo di f52bbf5, con lo stesso script copiato dentro
    git worktree add --detach <TMP> f52bbf5
    cp scripts/compare_canonical_vs_legacy_live.py <TMP>/mtb-graphrag/scripts/
    (cd <TMP>/mtb-graphrag && python scripts/compare_canonical_vs_legacy_live.py --out .../old_legacy_live.json)

    # confronto
    python scripts/compare_canonical_vs_legacy_live.py --diff \
      evaluation/canonical_runtime_forensics/old_legacy_live.json \
      evaluation/canonical_runtime_forensics/new_canonical.json

Lo script si adatta alla firma di `run_case` che trova: è per questo che gira
identico sui due commit. Nessuna rete: il solo trasporto HTTP è sostituito da
payload fissi, mentre scrittura dello snapshot, manifest, riletura dal disco,
parsing, selettore, gate e dossier sono codice di produzione.

## Fixture

| Fixture | Cosa mette alla prova |
|---|---|
| `cache_miss_api` | acquisizione autorizzata sul miss |
| `cache_hit` | seconda run sullo stesso documento, senza rete |
| `pmid_to_pmcid` | risoluzione PMID→PMCID e preferenza per il full text |
| `degraded_to_abstract` | degradazione dichiarata ad abstract quando PMC non è accessibile |
| `selector` | unità selezionate, hash del ranking, K |

## Campi confrontati

`candidate_ids` · `document_ids` · `document_availability` · `degradation` ·
`derived_pmcid` · `source_unit_ids` · `selector_selected_ids` · `selector_k` ·
`ranking_hash` · `model_input_source_unit_ids` · `gate_support_masks` ·
`status_assignments` · `dossier_hash` · `status` · `stopped_at`.

`runtime_flavour` e `run_case_parameters` sono **esclusi** dal confronto
semantico: il loro cambiamento è l'oggetto stesso della modifica, e includerli
direbbe soltanto che il refactor è avvenuto.

## Esito

    routing_changed             : true
    removed_parameters          : ["execution_mode"]
    added_parameters            : ["research_frozen_artifacts", "retrieve_fn"]
    semantic_result_unchanged   : true
    differences                 : []

Zero differenze su tutte e cinque le fixture, su tutti i campi confrontati.

## Cosa questo confronto **non** dimostra

Non è una validazione clinica, non misura qualità del recupero né correttezza
delle citazioni, e non sostituisce l'esecuzione con rete reale: i payload delle
fonti sono fissi, scelti per esercitare i percorsi, non per rappresentare la
letteratura. Dimostra una cosa sola, che è quella che serviva: fra i due commit
la pipeline percorre lo stesso cammino e produce gli stessi identificatori.

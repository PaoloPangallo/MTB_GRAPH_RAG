# Claim–Evidence Matrix

    protocol_version : mtb-graphrag-final-evaluation/1.0
    runtime_commit   : f52bbf5920c14324953be849e666bc84571957e9

Ogni affermazione della tesi è legata a un esperimento, a una metrica e a un
artefatto. Una claim senza riga in questa tabella non va scritta in tesi.

| # | Thesis claim | Evidence needed | Experiment | Metric | Artifact |
|---|---|---|---|---|---|
| C1 | La rappresentazione materializzata preserva i path del grafo senza inventarne | riderivazione indipendente dei path eleggibili | E1 (RQ1) | `materialization_precision`, `materialization_recall`, `field_completeness` su 46 864 | `rq1/` |
| C2 | Una fonte che nega l'associazione non diventa evidenza a supporto | sweep full-corpus sulla polarità | E2 (RQ1) | `does_not_support_promoted = 0 / 1 936`, `negative_source_primary_bucket = 0 / 1 936` | `rq1/negative_polarity_sweep.json` |
| C3 | Le proprietà semantiche di GCA 3.0 non sono attribuite al sistema valutato | verifica che il runtime legga 2.0 | E1 | `runtime_gca_version = 2.0`, nessun import di `kg_retrieval_v3` | `rq1/runtime_repository_binding.json` |
| C4 | La catena GCA → documento → SourceUnit → quote è ricostruibile end-to-end | esecuzione LIVE con provenance completa | E5, E7 (RQ2) | `document_resolution_rate`, `parser_success_rate`, catena di eventi completa | `rq2/`, `live_replay/` |
| C5 | Il selector generalizza oltre il corpus di sviluppo | corpus indipendente con gold congelato prima del selector | E3 (RQ2) | `HitRate@5` su 9/9 positivi **e** su 20 complessivi, `Recall@10`, MRR | `rq2/selector_comparison.json` |
| C6 | Il ranking deterministico batte First-K e BM25 sullo stesso materiale | confronto paired a tre bracci | E3 | delta con CI bootstrap paired, seed 20260809 | `rq2/baseline_comparison.json` |
| C7 | Sostituire il gold col selector non degrada la decisione a valle | confronto paired GOLD vs SELECTOR | E4 (RQ2) | `decision_concordance`, `validated_quote_rate`, `abstain_rate` su 9 e su 11 | `rq2/gold_vs_selector.json` |
| C8 | Un LLM non può modificare direttamente lo stato canonico | contratto di stage + test ostili | E5, E6 (RQ3) | transizioni non autorizzate `= 0 / N` | `rq3/authority_matrix.json` |
| C9 | Una quote fabbricata non entra mai nel dossier | batteria adversarial + ablation C | E6 (RQ3) | `wrong_quote_accepted = 0 / N`, delta vs `NO_QUOTE_VALIDATOR` | `ablations/quote_validator.json` |
| C10 | Un CaseContext non verificato non raggiunge il retrieval | ablation A su mismatch/incomplete/OOD/contradictory | E6 (RQ3) | `forbidden_retrieval_rate = 0 / N`, delta vs `NO_CASE_VERIFIER` | `ablations/casecontext_verifier.json` |
| C11 | Il layer di presentazione non può alterare il dossier | confronto payload con e senza narratore ostile + ablation D | E6 (RQ3) | `failed_narrative_presented = 0 / N`, identità del payload canonico | `ablations/narrative_verifier.json` |
| C12 | Ogni componente controlla una classe di fallimento distinta | quattro ablation paired | E6 (RQ3) | matrice `failure mode × ablation` | `tables/table6_safety_matrix.csv` |
| C13 | Il sistema si ferma in modo controllato sugli input che non deve trattare | testbed A per classe | E5 (RQ4) | `correct_path_rate`, `unexpected_exception_rate = 0 / 55` | `rq4/robustness_matrix.csv` |
| C14 | LIVE non richiede bundle congelati | run su documento mai visto, cache vuota | E7 | `frozen_bundle_access = 0`, `bundle_source_unit_ids_used = false` | `live_replay/unseen_document.json` |
| C15 | REPLAY è riproducibile e senza rete | run REPLAY sui 25 bundle | E8 | `network_calls = 0 / 25`, `live_selector_calls = 0 / 25`, accordo sugli hash | `live_replay/replay_reproducibility.json` |
| C16 | Il costo del cache miss è misurato, non stimato | confronto sullo stesso documento | E9 | latenza cache hit vs cache miss + API, separando i miss falliti | `latency/cache_hit_vs_miss.json` |
| C17 | Il recupero di citazioni esterne controllate non è parte del sistema | stato registrato di OncoKB | — | `oncokb_integrated_into_runtime = false` | `rq3_oncokb_fallback/aggregate_metrics.json` |

## Claim che NON possono essere fatte con gli artefatti disponibili

| Claim non sostenibile | Perché |
|---|---|
| «L'Eligibility Gate generalizza su input mai visti» | il gate è stato progettato dopo aver osservato i 35 casi del benchmark |
| «Il Narrative Verifier ha accuratezza 25/25» | il lexicon è stato corretto dopo 3 FAIL e le stesse narrative riverificate |
| «Il selector ha HitRate@5 del 100%» senza qualificazione | vale sui 9 casi positivi; sul denominatore complessivo di 20 è 0.45 |
| «Concordanza inter-annotatore umana» | il secondo pass è un passaggio di protocollo, non un secondo revisore umano |
| «Il sistema è clinicamente accurato» | non esiste gold clinico prospettico |
| «La pipeline interroga dinamicamente un knowledge graph» | il runtime legge un repository materializzato da export CSV congelato |

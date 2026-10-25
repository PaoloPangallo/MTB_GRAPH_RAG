# DATA_ASSETS

Questa mappa distingue sorgenti, asset congelati, output e ingressi esterni.
I contenuti di gold e segreti non sono stati aperti.

| Asset/path | Formato | Origine/versione | Lettore | Scrittore | Mutabilità | Ruolo |
|---|---|---|---|---|---|---|
| backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/ | JSON/JSONL | promoted repository 1.4 | loader, V3 backend | promozione | congelato | claim, parent, associations |
| backend/pipeline/evidence/corpus/v3/prototype_corpus_registry.json | JSON | registry 1.0 | loader | corpus tooling | congelato | path, hash, stato |
| backend/pipeline/evidence/corpus/v3/integrity/qualified_claim_repository_1_4.overlay.json | JSON | integrity overlay | loader | integrity tooling | congelato | verifica |
| backend/pipeline/evidence/corpus/promotion_contract.py | Python | repository/model/schema constants | loader/backend | maintainer | sorgente | bindability/policy |
| backend/pipeline/evidence/corpus/v3/ | JSON/JSONL/manifest | corpus V3 | loader/audit | builder/promoter | frozen | registry e lineage |
| schemas/ | JSON Schema | contratti | validator/test | tooling | sorgente | forma dati |
| benchmarks/mtb_evidence/v3/ | MD/JSON/JSONL/CSV | campagne V3 | audit/test | evaluation | misto | contratti/audit/output |
| benchmarks/mtb_evidence/pilot/ | CSV/JSON/MD | pilot | runner | pilot tooling | misto | input/report |
| benchmarks/mtb_evidence/final_experiment/ | manifest/JSON/CSV/MD | ufficiale | runner/test | build ufficiali | congelato | gold e run; referenziato |
| data/agent_events.sqlite3 | SQLite | run V2/agentico | EventLedger/replay | control runner | append-only | ledger |
| data/*.sqlite3 | SQLite | cache/run locali | legacy/tool | run locali | output | fuori V3 |
| logs/ | log | runtime | operatori | launcher/app | output | diagnostica |
| benchmarks/**/results, outputs, reports | JSON/JSONL/CSV/MD | run | report/test | runner | output | ufficiale o esplorativo |
| benchmarks/**/screenshots, *.png | PNG | verifiche UI | documentazione | browser/test | output | evidenza visiva |
| .env.example | env | template | launcher/config | maintainer | sorgente | nomi env senza segreti |
| .env | env | macchina | runtime | operatore | privato | valori non documentati |

## Ciclo di vita evidenza

Knowledge Graph/record originale → GraphEvidenceRecord → source unit →
qualified claim → repository materializzato → candidate → gate trace →
bucket → API response → UI. Il loader costruisce indici in memoria; non
interroga Neo4j nella route V3.

I campi che possono trasformarsi o non essere disponibili sono claim_text,
subject, relation, object, disease, biomarker, intervention, direction,
evidence type, PMID/DOI/NCT, URL/locator, parent record e source unit. Le
perdite osservate per il claim pilota sono tracciate in
[claim_data_contract_audit.md](../v3_pipeline_ui/claim_data_contract_audit.md).

## Knowledge Graph e provenance

backend/pipeline/cypher.py, helpers.py e api/subgraph.py interrogano Neo4j
nei percorsi legacy. Non è stato dimostrato un builder KG unico corrente
invocato dalla route V3; i builder benchmark sono classificati per evidenza
d'uso.

v3_result.py::build_provenance mantiene gli identificatori tecnici disponibili
nel repository. La provenance V3 è response data e non append del ledger. Il
ledger SQLite appartiene al controllo V2/agentico e scrive durante quei run.

## Ufficiale versus esplorativo

La mappa non apre gold né modifica ledger, corpus o output. final_experiment/
è frozen/reference-only; exploratory/, manual_* e scratch_* sono manuali o
esplorativi e non definiscono il runtime.

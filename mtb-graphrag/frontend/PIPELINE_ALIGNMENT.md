# Contratti verificati con il runtime

Il riferimento operativo e `backend/research_pipeline/orchestrator.py` e
`backend/api/research_routes.py`, non la documentazione storica della V3.

| Superficie | Contratto operativo | Correzione frontend |
| --- | --- | --- |
| Stage 7 | `live_resolution._preview_for`: `locator`, `lineage`, `text_preview`, `exact_text_available` | Legge campi annidati e distingue anteprima da citazione validata |
| Stage 6 | `DocumentResolution.to_preview`: `unavailable_count` distinto da `cache_misses` e `network_fetch_count` | Nessuna sottrazione dei contatori per inventare indisponibilita |
| Stage 10 | Validazione letterale, verifica strutturale, confronto semantico indipendente per EVIDENCE_DRUG, ammissione finale deterministica | Espone separatamente quote, supporto e verifica; descrive il contributo del modello |
| Stage 12 | Status e bucket interni del percorso di compatibilita | Non li presenta come supporto canonico o come risultato privo di input LLM |
| Stage 13 | Payload con `dossier` storico e `relation_aware_report` canonico | Output dedicato al report canonico |
| Dossier | `build_relation_aware_report`: PAPER_EVIDENCE, CLINICAL_TRIAL, KG_ONLY | Sezioni distinte; quote non validate escluse dalla presentazione come evidenze |
| Statement del grafo | Una entity di tipo Evidence puo avere come label un intero statement curato | Titolo mostra l'identificatore, evitando di promuovere testo del grafo a evidenza documentale |
| Provenienza | `/provenance` conserva `DOSSIER_ITEM` basato sugli status dello stage 12 e campi quote storici | Provenienza canonica primaria dal dossier; trace interna espandibile e identificata separatamente |
| SSE | `events.EVENT_TYPES` contiene anche cache, fetch, selezione SourceUnit e narrativa | Listener registrati per tutti i tipi nominati |
| Cambio run | Richieste REST e callback SSE possono completarsi dopo la navigazione | Generazione della sottoscrizione e callback invalidati dal cleanup; artefatti legati al run_id |
| Caricamento dossier | Risposta REST asincrona dopo la conclusione della run | Stato di caricamento esplicito, senza mostrare dossier di altre run |

## Limiti del contratto backend ancora presenti

`/metrics.llm_calls` conta le call dello stage 9, non tutte le chiamate LLM della
pipeline. I token di quell'endpoint riguardano lo stesso insieme. La durata
riportata e la somma delle durate degli stage. La UI usa quindi etichette Reader
e somma delle durate. `quotes_accepted` usa il suffisso ACCEPTED e non include
tutti gli esiti ammessi con riserva: non e l'aggregazione canonica del dossier.

Il producer dello stage 10 e dichiarato DETERMINISTIC nel runtime anche quando
il confronto semantico chiama un modello. I filtri indicano esplicitamente il
producer dichiarato; il testo dello stage descrive la verifica mista.

La fixture `src/research/__fixtures__/runtime-contract.json` e stata generata
dalle funzioni Python `_preview_for`, `build_relation_aware_report`,
`load_candidates` (repository 4.0) ed `EVENT_TYPES`, senza chiamate di rete o
inferenze LLM. Copre candidate reali nei tre rami con fonti non risolte.
I test di componente non costituiscono una verifica live dei provider o una
verifica visiva del browser.

La verifica successiva dei cinque casi effettivamente esposti dal frontend e
stata eseguita sul backend live. I risultati e le limitazioni sono in
`verification/frontend-demo-cases/REPORT.md`: tutte le run si fermano nel
parser con argomenti non validi, quindi non dimostrano il successo dei rami
documentali. I payload reali sono coperti dai test `liveDemoResults.test.tsx`
e dalle verifiche di integrazione della console.


## Viste Oncologo e Debug

La console apre la vista Oncologo: caso in esame, dossier, fonti, citazioni
validate, supporto e limitazioni. La navigazione del dossier collega Caso,
Pubblicazioni, Studi clinici, Knowledge Graph e Limiti. Gli identificativi
interni, i record del reader e i conteggi tecnici sono nella vista Debug,
insieme a stage, inspector, provenienza e metriche. Il selettore conserva
la stessa run; `?view=oncologist` e `?view=debug` permettono link diretti e
ripristino dopo refresh. In una run esistente il nuovo input e richiudibile.

Verifica: suite frontend 193 test passati; dopo le correzioni di accessibilita,
15 test mirati passati, typecheck e lint di `src` passati. Build riuscita.
Il lint globale e ostacolato dai permessi di una directory temporanea dei
test parser sotto `verification/`; browser non disponibile per QA visiva.

La successiva correzione parser 3.3 ha superato parser e gate in tutti i
cinque demo live autorizzati: vedere `verification/parser-repair/REPORT.md`.
Il precedente report dei fallimenti rimane una testimonianza storica.

## Architettura, narrazione e prestazioni

La sintesi narrativa ora precede il dossier; assenza e rifiuto sono spiegati
senza mostrare prosa non verificata. Debug apre con la mappa navigabile dei
percorsi PAPER, TRIAL e KG_ONLY, con stati aggregati degli stage dichiarati.
Le icone provengono da Material UI. Snapshot ed eventi di avanzamento sono
compatti, gli eventi REST incrementali e paginati, gli output completi degli
stage e i moduli Debug caricati su richiesta. Il ledger e le API complete
restano disponibili. Misure e limiti: `verification/UI_PERFORMANCE.md`.
Verifica finale: 199 test frontend, 2 test API di proiezione, build,
typecheck e lint del codice superati.

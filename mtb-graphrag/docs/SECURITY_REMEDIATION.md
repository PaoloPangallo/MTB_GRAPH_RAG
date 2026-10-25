# Remediation delle credenziali

**Data:** 21 luglio 2026 · **Branch:** `feat/model-selection-and-pilot-evaluation`

Questo documento registra un audit delle credenziali del repository e le correzioni
applicate. **Non contiene alcun valore sensibile**: i segreti sono descritti per
posizione e tipo, mai per valore.

---

## ⚠️ Azioni manuali obbligatorie

Le correzioni al codice **non annullano l'esposizione già avvenuta**. Due credenziali
sono presenti nella cronologia Git e vanno considerate compromesse.

| # | Credenziale | Dove | Azione |
|---|---|---|---|
| 1 | Password Neo4j | 5 commit in cronologia | **Ruotare** sull'istanza Neo4j, poi aggiornare `.env` |
| 2 | Chiave API NCBI E-utilities | 1 commit in cronologia | **Revocare e rigenerare** su NCBI, poi definire `NCBI_API_KEY` nell'ambiente |

Nessuna delle due è stata cambiata automaticamente: modificare una password di
database o revocare una chiave API sono azioni con effetti fuori dal repository, e
vanno decise da chi amministra i servizi.

Finché la rotazione non avviene, chiunque abbia accesso alla cronologia del
repository — inclusi eventuali fork o cloni — dispone di entrambe le credenziali.

---

## 1. Metodo dell'audit

```bash
git ls-files '*env*'                     # quali file di ambiente sono tracciati
git check-ignore -v .env mtb-graphrag/.env
git log --all -S'<segreto>' --oneline    # presenza in cronologia
git grep -n -E 'getenv\(...\)' -- '*.py' # fallback nel codice versionato
```

La scansione è stata condotta sui file **tracciati da git**, non sul working tree: è
ciò che finisce in un clone a determinare l'esposizione.

## 2. Stato dei file di ambiente

Corretto già prima di questo intervento, verificato e ora coperto da test:

- **nessun `.env` reale è tracciato.** L'unico file versionato è
  `mtb-graphrag/.env.example`.
- `.gitignore` (righe 8-9) copre sia `.env` sia `mtb-graphrag/.env`, confermato con
  `git check-ignore -v`.
- `.env.example` contiene solo placeholder: `NEO4J_PASSWORD=`, `OLLAMA_API_KEY=`,
  `ONCOKB_TOKEN=`, `NCBI_EMAIL=` sono tutti vuoti.

## 3. Password Neo4j — 16 file corretti

Il pattern era sempre lo stesso:

```python
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "<password reale>")
```

Un default del genere è peggio di una variabile mancante: lo script funziona, quindi
nessuno si accorge che il segreto è versionato, e chiunque legga il repository lo
ottiene.

**File corretti** (14 via `require_env`, 2 con correzione mirata):

<details>
<summary>Elenco completo</summary>

- `analisi/analisi.py`
- `create_notebook.py` (2 occorrenze, in codice generato)
- `data_expl/benchmark/recalc_metrics.py`
- `data_expl/scratch/reload_neo4j.py` (assegnazione diretta, non `getenv`)
- `scratch/check_breast_cancer_pertuzumab_target.py`
- `scratch/check_disease_kws.py`
- `scratch/check_evidence_statement_pertuzumab.py`
- `scratch/check_pertuzumab_evidence.py`
- `scratch/check_pertuzumab_rels.py`
- `scratch/find_pertuzumab.py`
- `scratch/inspect_db.py`
- `scratch/inspect_pertuzumab_combo.py`
- `scratch/inspect_trastuzumab.py`
- `scratch/run_cypher_erbb2.py`
- `scratch/test_query.py`
- `scratch/update_pertuzumab_graph.py`

</details>

Nuovo helper condiviso `utility/credentials.py`:

```python
NEO4J_PASSWORD = require_env("NEO4J_PASSWORD")
```

`require_env` non ha alcun valore di ripiego. Se la variabile manca, solleva
`MissingCredentialError` con un messaggio che indica quale variabile serve e in quali
file può essere definita — senza mai riportarne il valore.

## 4. Chiave API NCBI — 2 file corretti

**Trovata dal nuovo test, non dall'audit precedente.** Era un'assegnazione diretta a
un letterale, quindi sfuggiva a qualunque ricerca sul pattern `getenv`:

- `utility/download_benchmark.py`
- `utility/download_benchmarkv2.py`

Ora usa `optional_env("NCBI_API_KEY")`. È genuinamente opzionale — senza chiave le
E-utilities applicano un rate limit più basso, e il codice lo gestiva già — ma
opzionale non significa che debba stare nel codice.

## 5. Artefatti statici bonificati

La password compariva anche in notebook e loro export, dove era stata catturata
insieme all'output di esecuzione:

| File | Occorrenze |
|---|---:|
| `esplorazione_kb_oncologico.ipynb` | 2 |
| `esplorazione_kb_oncologico_executed.ipynb` | 2 |
| `data_expl/esplorazione/esplorazione_kb_oncologico.ipynb` | 2 |
| `data_expl/esplorazione/esplorazione_kb_oncologico.html` | 1 |
| `data_expl/scratch/test_nb.txt` | 2 |

Sostituita con `REDACTED_SEE_docs_SECURITY_REMEDIATION`. La validità JSON dei tre
notebook è stata verificata dopo la modifica.

## 6. Il detector non contiene più il segreto

Lo scrubber dell'audit (`audit_lib/serialize.py`) elencava la password come costante
per poterla riconoscere negli artefatti. Era autolesionista: per rilevare un segreto
lo manteneva versionato.

Ora i valori extra da rimuovere arrivano dalla variabile `AUDIT_EXTRA_SECRETS`
(valori separati da virgola), e il test corrispondente confronta gli artefatti con i
segreti letti dall'ambiente invece che con letterali.

## 7. Test di regressione

`mtb-graphrag/backend/tests/test_security_no_hardcoded_credentials.py`, 9 test, tutti
offline:

| Test | Cosa impedisce |
|---|---|
| `test_no_secret_env_var_has_a_non_empty_default` | il ritorno del pattern `getenv("SEGRETO", "valore")` |
| `test_no_direct_credential_assignment` | assegnazione diretta di una credenziale a un letterale |
| `test_no_uri_with_embedded_userinfo` | URI del tipo `bolt://utente:password@host` |
| `test_no_real_env_file_is_tracked` | che un `.env` reale finisca sotto controllo di versione |
| `test_env_example_has_no_secret_values` | che il template acquisisca valori reali |
| `test_gitignore_covers_env_files` | rimozione della regola da `.gitignore` |
| `test_require_env_fails_readably_when_missing` | che il fallimento torni a essere oscuro |
| `test_require_env_returns_the_environment_value` | regressione funzionale dell'helper |
| `test_error_message_never_contains_a_value` | che il messaggio d'errore riveli il segreto |

Il secondo test ha trovato la chiave NCBI durante la sua prima esecuzione. È il motivo
per cui è stato scritto come scansione dei file tracciati e non come lista di pattern
noti.

## 8. Cronologia Git — non riscritta

`git log -S` conferma la presenza dei segreti nella cronologia:

- password Neo4j: **5 commit**
- chiave NCBI: **1 commit**

**La cronologia non è stata riscritta.** Un `filter-repo` o un rebase riscriverebbe
gli SHA di tutti i commit discendenti, invalidando i riferimenti già citati negli
artefatti dell'audit — incluso il `commit_sha` registrato in
`graph_snapshot_manifest.json` — e romperebbe qualunque clone esistente. È una
decisione che spetta a chi possiede il repository.

La rotazione delle credenziali rende comunque innocua l'esposizione storica, ed è
l'azione da fare per prima. La riscrittura della cronologia, se desiderata, viene
dopo e non la sostituisce.

## 9. Residui noti, fuori controllo di versione

La password compare ancora in file **non tracciati** e coperti da `.gitignore`:

- `.ipynb_checkpoints/` (due file)
- `.virtual_documents/` (un file)
- `data_expl/esplorazione/.ipynb_checkpoints/` (un file)

Non sono un'esposizione del repository, ma sono il segreto su disco. Non li ho
modificati perché sono artefatti locali dell'utente. Si eliminano senza perdita:

```bash
rm -rf .ipynb_checkpoints .virtual_documents data_expl/esplorazione/.ipynb_checkpoints
```

## 10. Checklist

- [x] Fallback di password rimossi da 16 file
- [x] Chiave API NCBI rimossa da 2 file
- [x] Helper centralizzato con fallimento leggibile
- [x] Artefatti statici bonificati
- [x] Detector ripulito dal letterale
- [x] `.gitignore` e `.env.example` verificati
- [x] 9 test di regressione, verdi
- [ ] **Rotazione della password Neo4j** — manuale
- [ ] **Revoca e rigenerazione della chiave NCBI** — manuale
- [ ] Eliminazione dei checkpoint locali — manuale, opzionale
- [ ] Riscrittura della cronologia — da valutare, non automatizzabile

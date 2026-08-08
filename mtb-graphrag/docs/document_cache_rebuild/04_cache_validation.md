# Validazione della cache

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `cache_validation.json`.

## 1. Loader reale, non ispezione del filesystem

La verifica non conta file: chiama le stesse funzioni che il runtime chiama.

```
validate_cache()  ->  (True, [])
is_available()    ->  True
```

Nessun reason code. Prima della ricostruzione era
`(False, ['CACHE_PATH_NOT_FOUND'])`.

## 2. Descrittore esposto da `/config`

```json
{
  "document_cache_available": true,
  "cache_path_redacted": ".../data_cache/document_grounding",
  "cache_version": "authorized-document-cache/1.0",
  "reason_codes": [],
  "manifest_hash": "ece9d25d74b3050f222343d3f31dc22d20d39d1883957f431c4280ef9326006b",
  "manifest_rows": 43,
  "document_count": 40,
  "documents_with_text": 40,
  "documents_unavailable": 3,
  "source_unit_count": 3402
}
```

Ogni campo coincide con quello documentato per la cache del pilot in
[../verifiable_pipeline/document_cache_runtime.md](../verifiable_pipeline/document_cache_runtime.md)
§4. Il `manifest_hash` è identico perché il manifest non è stato toccato.

## 3. Corrispondenza manifest → payload

`describe()` non si fida della presenza della directory: per ogni riga con
`local_cache_path` verifica `(root / relative).is_file()`.

| Metrica | Valore |
|---|---:|
| `manifest_document_count` | 43 |
| `payload_found_count` | 40 |
| `payload_missing_count` | 3 |
| `expected_unavailable_count` | 3 |
| **`unexpected_missing_count`** | **0** |

I 3 mancanti sono esattamente i 3 attesi: nessuna sorpresa.

## 4. Layout

```
data_cache/document_grounding/
├── pubmed/
│   ├── abstracts/     17 file
│   └── metadata/      17 file
├── pmc/
│   └── xml/           11 file
├── clinical_trials/   12 file
├── local_pdf/          0 file
├── manifests/          1 file   (stato del bootstrap)
└── errors/             0 file
```

`validate_cache()` richiede `pubmed/`, `pmc/` e `clinical_trials/`. Le altre tre
directory sono create dal costruttore di `AuthorizedDocumentCache` e non sono un
requisito del runtime.

## 5. Isolamento da Git

```
$ git check-ignore -v data_cache/
.gitignore:68:data_cache/	data_cache/

$ git status --porcelain | grep data_cache
(nessun risultato)
```

Nessun payload è tracciato, e nessuno può esserlo per distrazione.

# RQ3 — Fattibilità tecnica del fallback OncoKB

Complemento a `licensing_report.md`. Quello stabilisce che manca il permesso
esplicito richiesto dalla licenza; questo stabilisce che, **anche con quel
permesso**, il pilot previsto dal protocollo non sarebbe eseguibile su questo
corpus.

## Ipotesi da valutare (§13)

> OncoKB può essere interrogato **soltanto** quando la candidate non possiede
> identificatori documentali utili.

La popolazione bersaglio è quindi l'insieme delle candidate senza PMID: **38 634
su 46 864 (82.4 %)**.

## Chiavi richieste dagli endpoint OncoKB

Dalla documentazione ufficiale, l'endpoint di annotazione principale è
`GET /api/v1/annotate/mutations/byProteinChange`, con:

| Parametro | Obbligatorio | Note |
|---|---|---|
| `hugoSymbol` / `entrezGeneId` | **sì** (uno dei due) | OncoKB è indicizzato per gene |
| `alteration` | no, ma **necessario nei fatti** | senza alterazione la risposta non individua un'evidenza specifica |
| `tumorType` | no | senza tumor type l'evidenza non è selezionabile per indicazione |

L'evidenza OncoKB — e quindi le citazioni che restituisce — è chiavizzata su
**(gene, alterazione, tipo di tumore, farmaco)**. Una query priva di alterazione
e di tipo di tumore non individua una relazione: individua un gene.

## Interrogabilità della popolazione bersaglio

Profilo delle 38 634 candidate senza PMID:

| Profilo (gene / alteration / disease / intervention) | Candidate |
|---|---|
| `gene / — / — / intervention` | 25 589 |
| `— / — / — / intervention` | 7 381 |
| `gene / — / — / —` | 5 664 |

| Stato di interrogabilità | Candidate |
|---|---|
| `QUERYABLE` | **0** |
| `QUERYABLE_WITHOUT_TUMOR_TYPE` | **0** |
| **`NOT_QUERYABLE`** | **38 634 (100 %)** |

**Nessuna** delle candidate prive di PMID possiede un'alterazione; **nessuna**
possiede una disease. 7 381 non possiedono nemmeno un gene.

Il motivo è strutturale e discende da RQ1: alteration, disease e direction
esistono **solo** sulle regole derivate da record Evidence
(`evidence-statement`, `evidence-to-drug`) — che sono esattamente e
completamente le 8 230 candidate che **hanno già** un PMID. Le regole prive di
PMID (`gene-drug-interaction`, `trial-drug`, `trial-gene`,
`companion-diagnostic`) non trasportano quel contesto.

> Le candidate che avrebbero bisogno del fallback sono precisamente quelle che
> non possiedono le chiavi con cui il fallback andrebbe interrogato.

## Stratificazione richiesta dal protocollo (§15)

| Strato richiesto | Candidate disponibili |
|---|---|
| gene + alteration + disease | **0** |
| gene + disease senza alteration | **0** |
| sensitivity | **0** |
| resistance | **0** |
| intervention evaluation | 32 970 |
| therapy discovery | 5 664 |
| candidate con NCT ma senza PMID | 12 882 |
| candidate senza alcun identificatore | 25 752 |

Quattro degli otto strati sono **vuoti**. Il campione di 20 candidate previsto
dal protocollo non è costruibile secondo la stratificazione richiesta.

## I quattro casi di attivazione (§13), rivalutati

| Caso | Popolazione | Valutazione |
|---|---|---|
| **A** `NO_DOCUMENT_IDENTIFIER` | 25 752 | Nessuna è interrogabile: manca alteration, disease e — per 7 381 — il gene |
| **B** `PMID_NOT_RESOLVABLE` | 2 candidate (PMID `174591`) | Popolazione troppo piccola per un pilot; il caso ha però alteration e disease, quindi **sarebbe** interrogabile |
| **C** `DOCUMENT_UNAVAILABLE` | 2 214 PMID su 2 229 | Il documento manca, ma **la citazione esiste**: il problema è di accesso al testo, non di assenza di fonte. OncoKB non lo risolve |
| **D** `NO_EXPLICIT_SUPPORT` | non misurato | Richiede annotazione umana (RQ2). Usare OncoKB qui significherebbe cercare una fonte più favorevole dopo che il documento non ha sostenuto la candidate — **esplicitamente vietato** dal §13 |

I quattro casi **non** richiedono lo stesso fallback, e nessuno dei quattro è
risolto da OncoKB su questo corpus. Il caso C è particolarmente istruttivo:
riguarda 2 214 PMID e sarebbe la maggioranza dei fallimenti, ma è un problema di
disponibilità del full text, non di mancanza di citazione.

## Oggetto di fallback

`evaluation/rq3/models.py` definisce `ExternalCitationCandidate` a livello
**puramente sperimentale**, fuori dai modelli del runtime. L'invariante è
codificata: `validate()` solleva un errore se
`promoted_to_documentary_support` è vero. Un risultato OncoKB non modifica la
GraphCandidateAssertion originale e non è supporto documentale finché non ha
attraversato Document Resolution → SourceUnit → Paper Selection → Paper Context
Enricher → Validator.

## Esito

```
oncokb_calls_executed            = 1   (GET /api/v1/info, solo metadata)
oncokb_knowledge_data_retrieved  = false
oncokb_pilot_executed            = false
oncokb_integrated_into_runtime   = false
coverage_gain_measured           = null
```

**Decisione: `ONCOKB_FALLBACK_LOW_YIELD`** sul piano tecnico, in concorso con
**`ONCOKB_FALLBACK_BLOCKED_NO_AUTHORIZATION`** sul piano della licenza.

Il pilot non è stato eseguito. Eseguirlo avrebbe consumato chiamate verso una
risorsa licenziata per dimostrare un esito già determinato dalla struttura del
corpus.

## Cosa servirebbe perché il fallback diventi valutabile

1. Permesso scritto di OncoKB per l'uso in benchmarking (`contact@oncokb.org`).
2. Una materializzazione che propaghi **alteration e disease anche alle regole
   non-Evidence** — cioè la correzione del limite che RQ1 documenta. Senza di
   essa la popolazione bersaglio resta non interrogabile qualunque sia la
   licenza.
3. Una decisione esplicita su come trattare il caso C (`DOCUMENT_UNAVAILABLE`),
   che è quantitativamente il problema dominante e che OncoKB non affronta.

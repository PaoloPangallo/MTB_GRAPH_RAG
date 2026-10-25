# Implicazioni architetturali

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**
**Analisi, non mandato di implementazione.**

## 1. Cosa la sonda ha stabilito

| Anello della catena | Automatizzabile | Prova |
|---|---|---|
| candidate → identificatore | **sì** | `document_identifiers` della GCA, letto senza input umano |
| PMID → PMCID | **sì** | dichiarato da PubMed in `ArticleId IdType="pmc"` |
| identificatore → documento | **sì** | E-utilities e PMC OAI, 3 casi su 3 |
| documento → SourceUnit con testo | **sì** | parser esistenti, 0 fallimenti |
| SourceUnit → Gemma | **sì** | contratto invariato, 3 casi su 3 |
| quote → verifica | **sì** | validatore deterministico, offset ritrovato |
| cache miss → snapshot | **sì** | ramo esercitato, snapshot creato |
| fonte nega → nessuna evidenza | **sì** | nessun documento sostitutivo |

Il clinico non deve conoscere alcun identificatore.

## 2. Il problema che la sonda ha scoperto, e che non era la domanda

Il recupero del documento è automatizzabile. **La scelta del passaggio da
mostrare al modello non lo è ancora.**

Oggi le unità che raggiungono Gemma provengono da `bundle["source_unit_ids"]`:
un artefatto congelato, costruito una volta dal pilot. `paper_selection` le
usa, non le calcola. Su un documento recuperato al volo quel bundle non esiste.

La sonda l'ha misurato per differenza: su un full text di 243 unità, prendere le
prime quattro significa mostrare titolo e introduzione. Il modello ha comunque
risposto correttamente — ma perché quel documento davvero non sosteneva la
candidate, non perché la selezione fosse buona.

**Una architettura cache-first/API-on-miss ha quindi bisogno di due componenti,
non di uno:**

1. il resolver documentale — dimostrato fattibile qui;
2. un selettore di SourceUnit deterministico e documentabile, che oggi non
   esiste come componente autonomo.

Il secondo è il lavoro vero, ed è anche quello dove si annidano le decisioni
metodologicamente delicate: selezionare passaggi in base alla loro somiglianza
con la candidate significa introdurre un criterio di rilevanza che oggi non c'è.

## 3. Cosa non va toccato

Le proprietà che rendono verificabile la pipeline attuale non sono ostacoli da
rimuovere:

- `ReadOnlyDocumentCache` non deve acquisire capacità di rete. Un eventuale
  fetch-on-miss deve stare **fuori** dal percorso di lettura, come sta oggi il
  bootstrap.
- Il fallimento deve restare un esito. `DOCUMENT_UNAVAILABLE` non deve diventare
  «riprova con qualcos'altro».
- Ogni documento materializzato al volo deve entrare nel manifest con
  `retrieved_at`, `content_hash` e `license_status`, o la provenance si spezza.
- Il closed set deve restare dichiarato. Un resolver che scopre documenti nuovi
  non è più un resolver: è un motore di ricerca, e cambia la natura degli
  esperimenti.

## 4. Rischi da istruire prima di decidere

| Rischio | Perché conta |
|---|---|
| Snapshot mutevoli | PMC cambia payload a ogni richiesta; senza snapshot immutabile la riproducibilità di una run si perde |
| Latenza e rate limit | 3 req/s su NCBI; una run con cache miss multipli diventa lenta e fragile |
| Licenze | Il full text PMC non è redistribuibile in modo uniforme; materializzare è diverso da conservare |
| Selezione delle unità | Vedi §2: è la decisione metodologicamente rischiosa |
| Contaminazione degli esperimenti | Se il corpus può crescere a runtime, i benchmark congelati smettono di essere confrontabili |

## 5. Raccomandazione

La direzione è tecnicamente percorribile e vale la pena istruirla. Ma non è una
funzionalità da aggiungere al runtime attuale: è un secondo runtime, con un
proprio contratto di provenance, che condivide i parser e la cache in lettura.

Nessuna modifica architetturale è giustificata da questa sonda da sola. Ciò che
la sonda giustifica è **aprire il progetto del selettore di SourceUnit**, senza
il quale l'anello finale resta scoperto.

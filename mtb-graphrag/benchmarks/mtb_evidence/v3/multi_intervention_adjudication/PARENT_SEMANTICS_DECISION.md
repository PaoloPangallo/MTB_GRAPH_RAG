# Semantica del parent

**Decisione: `parent_is_provenance_container`**

Decisa da `author_adjudicator`. Approvazione automatica della raccomandazione:
no.

## Perche'

1. Tre gruppi rendono la semantica di claim insostenibile, e non per un difetto di annotazione. In evidence:275 il parent afferma erlotinib mentre la fonte nomina solo 'EGFR-TKI'. In evidence:1851 e evidence:1853 afferma infigratinib mentre la fonte usa solo BGJ398. In evidence:4759 lega L858R/ex19del a un esito misurato sulle mutazioni non comuni. Se il parent e' un claim, sono quattro claim falsi da rimuovere. Se e' un contenitore, non afferma nulla e il problema si sposta dove appartiene: quali claim la fonte sostenga davvero.
2. Il parent nasce da una scelta dell'adapter, non da una lettura della fonte: davanti a un record V2 multi-intervento l'adapter promuove il primo valore scalare. Quella scelta non e' un giudizio documentale e non dovrebbe produrre una proposizione terapeutica.
3. La simulazione della prima revisione conservava 13 parent e aggiungeva 8 figli, cinque dei quali sullo stesso intervento del parent. Quella configurazione e' coerente solo se il parent smette di essere interrogabile come claim; altrimenti la stessa affermazione esiste due volte.
4. Il confronto fra le due revisioni ha mostrato che l'intero scarto sui figli (8 contro 3) dipende da questa scelta e da nient'altro: sulle cinque associazioni contese le due letture documentali coincidono.

## Cosa il parent conserva

- `graph_evidence_id`
- `original_v2_record`
- `source_identity`
- `provenance`
- `raw_fields`
- `adapter_lineage`
- `non_materialized_associations`
- `review_state`

## Cosa il parent smette di fare

- `counted_as_therapy_claim`
- `classified_as_autonomous_therapeutic_support`
- `returned_as_primary_claim`
- `evaluated_in_claim_level_metrics`
- `used_as_automatic_substitute_for_the_first_child`

## Alternative considerate

### `parent_is_therapeutic_claim`

A favore:

- Nessuna migrazione: e' il comportamento attuale dell'adapter e del corpus.
- Nessun claim da creare per gli interventi gia' rappresentati, quindi meno record.

Perche' e' stata scartata:

- Obbliga a conservare quattro proposizioni terapeutiche che la fonte non sostiene, oppure a rimuoverle una per una senza un principio.
- Non lascia posto ai risultati aggregati e ai regimi: in evidence:275 e nei due gruppi FGFR2 il risultato esiste ma non e' di nessun farmaco singolo, e un modello a soli claim atomici non puo' rappresentarlo.
- Rende il claim dipendente dall'ordine dei valori nell'adapter.

### `mixed_parent_semantics`

A favore:

- Lascerebbe claim i parent ben sostenuti e degraderebbe a contenitore solo quelli problematici.
- Migrazione piu' piccola, limitata ai casi difettosi.

Perche' e' stata scartata:

- Il tipo del parent dipenderebbe dallo stato della revisione, quindi cambierebbe nel tempo per lo stesso record: l'identita' del claim non sarebbe stabile.
- Il retrieval dovrebbe interrogare due semantiche diverse nello stesso indice e le metriche claim-level non avrebbero un denominatore definito.
- Sposta il problema invece di deciderlo: ogni nuovo gruppo richiederebbe di stabilire prima che cosa sia il suo parent.

## Conseguenze accettate

- I 13 statement operativi corrispondenti smettono di essere claim e vanno deprecati come tali.
- Ogni proposizione terapeutica va materializzata esplicitamente, anche quando coincide con l'intervento che il parent portava.
- Le metriche claim-level cambiano denominatore: il confronto con le misure precedenti non e' diretto.
- Un gruppo puo' restare senza alcun claim, come evidence:3811 e evidence:4759, e questo e' un esito legittimo e non una perdita da compensare.

## Cosa questa decisione non decide

- La politica di gerarchia fra claim (fuori perimetro).
- Se un claim aggregato di classe debba essere restituito dal retrieval primario o solo come contesto.
- La soglia minima di forza dell'evidenza per la materializzazione.

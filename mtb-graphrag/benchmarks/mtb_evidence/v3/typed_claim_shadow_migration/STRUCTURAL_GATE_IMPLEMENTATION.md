# Gate strutturale claim-type-aware

Versione gate: `claim_structural_gate/1.0`
Contratto applicato: `claim-type-retrieval-contract/1.0`

## L'inversione

Nella pipeline operativa un candidato entra nel ranking e poi viene penalizzato.
Nel modello shadow un candidato entra nel ranking soltanto se il gate lo ammette,
e il gate non sa nulla del punteggio.

La differenza non e' di stile. Una penalita' e' un numero, e un numero si compensa
con altri numeri: `penalty_pending_terminology` vale `-3` contro un
`native_biomarker` che vale `40`, quindi un mapping non verificato resta
competitivo. Le quattro condizioni che le penalita' codificavano non sono
"evidenza meno buona da scontare": sono evidenza che non appartiene al ranking
primario, e va detto con l'appartenenza, non con l'aritmetica.

## Ordine di valutazione

1. generazione dei candidati (perimetro nativo);
2. classificazione della query;
3. match strutturale tipizzato → `intervention_match_type`;
4. vincoli nativi → eventuale `rejected_by_native_constraints`;
5. invarianti dell'oggetto (deprecato, audit-only);
6. bucket;
7. **solo qui** eventuale punteggio.

Lo scoring shadow rifiuta di calcolare su un candidato respinto dai vincoli
nativi: `features_for` solleva. Vederlo aprirebbe la possibilita' di ripescarlo.

## Tabelle di decisione

Non sono ridefinite qui. Vengono da
`benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py`, congelato
nella fase precedente, che resta l'unica fonte di verita' su quali match type
siano primary, warning o audit. Questo modulo le applica agli oggetti tipizzati
invece che ai dizionari della simulazione.

Vi aggiunge due condizioni che dipendono dall'oggetto e non dalla query, e che
per questo non potevano stare in una tabella indicizzata per match type:

**Claim deprecato.** Non e' un candidato, qualunque sia il suo match type. Viene
declassato ad audit con `CLAIM_DEPRECATED`.

**Associazione.** `UnsupportedAssociation` e `UnresolvedAssociation` portano
`audit_only = true` come invariante dichiarato del modello. La tabella dei match
type e' piu' permissiva — `unresolved` e' anche warning-eligible, perche' quel
match type puo' descrivere anche un *claim* la cui attribuzione documentale e'
sospesa — ma un'associazione non e' un claim e non entra nel bucket dei
risultati trattenuti con avviso. L'invariante dell'oggetto ha la precedenza
sull'eleggibilita' del tipo di match. La tabella congelata non e' stata toccata.

## I quattro bucket

| Bucket | Contenuto |
|---|---|
| `primary_ranked_results` | atomic exact/normalized/verified alias, exact regimen, exact intervention class, query senza vincolo di intervento su claim compatibile |
| `retained_with_warning` | componente di regime, membro di aggregato non separabile, membro di classe verificato, regimen subset/superset, direzione correlata non equivalente |
| `audit_only_results` | parent, unsupported, unresolved, mapping pending, relazione di classe non verificata, claim deprecato |
| `rejected_by_native_constraints` | biomarcatore, disease, direzione o polarita' incompatibili; intervento incompatibile |

Un oggetto respinto dai vincoli nativi non finisce in audit: e' fuori perimetro,
e tenerlo in audit riempirebbe il bucket di oggetti irrilevanti per quella query.

## Generazione dei candidati

I parent vengono presentati solo se il loro `biomarker_context` coincide con il
biomarcatore della query. Il gate congelato manda ogni parent in audit senza
guardare il biomarcatore — nella simulazione della fase precedente i parent non
ne portavano uno — e valutarli tutti contro ogni query produrrebbe 147 righe di
audit per query, rendendo illeggibile cio' che invece va guardato. E' un filtro
di generazione dei candidati, non una decisione di gate: nessun oggetto cambia
bucket, alcuni semplicemente non vengono presentati. E' lo stesso argomento che
il contratto usa per i claim fuori perimetro.

## Simulazione sulle query congelate

`shadow_gate_simulation.jsonl` contiene l'esito delle 16 query del contratto
contro l'intero repository shadow. Distribuzione: 42 primari, 8 con avviso, 281
in audit.

| Query | Scenario | Esito |
|---|---|---|
| Q01 | no intervention | claim compatibili in primario, parent in audit |
| Q02 | single atomic exact | primario |
| Q03 | componente di regime | **solo warning**, mai primario |
| Q04 | exact regimen | primario |
| Q05 | regimen subset | warning, `REGIMEN_SET_DOES_NOT_COINCIDE` |
| Q06 | regimen superset | warning, `REGIMEN_SET_DOES_NOT_COINCIDE` |
| Q07 | exact class | primario sull'aggregato di classe |
| Q08 | class member | l'aggregato resta in audit (`unresolved_class_relation`); il farmaco raggiunge solo i claim atomici che lo nominano davvero |
| Q09 | aggregate member | warning, `AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION` |
| Q10 | mapping pending | audit, mai exact |
| Q11 | unsupported | le associazioni restano in audit, i claim legittimi restano primari |
| Q12 | unresolved | le associazioni restano in audit |
| Q13 | negative direction | primario, polarita' conservata |
| Q14 | reduced sensitivity | warning, `REDUCED_SENSITIVITY_IS_NOT_RESISTANCE` |
| Q15 | multi intervento non dichiarato | nessun exact regimen: i farmaci restano vincoli alternativi |
| Q16 | exact regimen (secondo) | primario, componenti non promossi |

Il gold non e' stato usato per nessuna di queste verifiche.

## I pesi non aggirano il gate

`legacy_penalty_bypass_tests.json` prende ogni candidato non primario — 288 casi
— e gli applica punteggi ipotetici di 0, 1, 1 000 e 999 999. In nessun caso il
bucket cambia; nessun candidato raggiunge il bucket primario. La funzione che
calcola il bucket accetta un punteggio come argomento proprio per rendere
verificabile che non lo usi.

Le quattro penalita' legacy restano nella configurazione operativa, invariate:

| Penalita' | Valore operativo | Sostituita nel modello shadow da |
|---|---|---|
| `penalty_pending_terminology` | −3 | `mapping_pending` → audit |
| `penalty_not_separable` | −2 | `aggregate_member_related` → warning |
| `penalty_unresolved` | −1 | `unresolved` → audit |
| `penalty_invalid` | −50 | `unsupported` → audit |

Nel percorso shadow nessuna delle quattro decide l'eleggibilita' primaria e
nessuna e' necessaria per impedire la promozione: sono registrate come
`legacy_feature_not_operational`.

## Output tipizzato

`intervention_representation` assume uno di cinque valori — `atomic`, `regimen`,
`class`, `aggregate`, `none` — e sopravvive fino al consumatore finale. Quattro
divieti sono controlli che sollevano:

- un regime non puo' uscire con meno di due componenti;
- un aggregato non puo' uscire ridotto a un membro;
- un parent non puo' uscire in un bucket diverso da audit o rejected, ne' come
  evidenza positiva;
- un'associazione non puo' uscire come evidenza positiva ne' nel bucket
  primario.

`none` non e' un valore mancante: e' l'affermazione che non c'e' un intervento da
rappresentare.

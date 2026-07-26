# Migrazione shadow al modello tipizzato parent/claim

Versione modello: `qualified_claim_model/1.0`
Versione repository: `qualified_claim_repository/1.0`
Stato: `shadow_not_promoted`

Il corpus operativo non e' stato promosso, modificato o rigenerato. Questa fase
costruisce accanto alla pipeline corrente una rappresentazione tipizzata degli
stessi dati e la verifica; non la mette in produzione.

## Cosa cambia, e perche'

L'adapter operativo raggruppa le righe V2 per graph evidence ID e, sui campi
multi-valore, tiene il primo valore. La riga di lineage lo chiama con precisione:
`v2_adapter.merge_duplicate_records.scalar_single_value_selection`. Il risultato
e' che `evidence:229` diventa uno statement su erlotinib e gefitinib sparisce, e
che quattro statement affermano cose che le loro fonti non dicono:

- `evidence:275` afferma erlotinib mentre la fonte nomina solo `EGFR-TKI`;
- `evidence:1851` e `evidence:1853` affermano infigratinib mentre la fonte usa
  solo BGJ398;
- `evidence:4759` lega L858R/ex19del a un esito misurato sulle mutazioni non
  comuni.

Il modello tipizzato non risolve il problema scegliendo meglio il primo farmaco.
Lo risolve togliendo l'affermazione dal contenitore: il record V2 diventa un
`GraphEvidenceRecord`, che conserva tutti gli interventi come letterali e non
afferma nessuna terapia. I claim nascono altrove, dove la revisione documentale
li sostiene.

## Conteggi derivati

Tutti i numeri qui sotto sono calcolati dagli artefatti e verificati dai test.
Nessuno e' codificato a mano.

| Grandezza | Valore |
|---|---|
| Parent (graph evidence ID) | 147 |
| Claim totali | 146 |
| — dall'adjudication | 15 |
| — legacy migrati | 131 |
| Atomic adjudicati | 9 |
| Aggregate adjudicati | 3 |
| Regimen adjudicati | 3 |
| Unsupported association | 6 |
| Unresolved association | 6 |
| Statement legacy deprecati | 13 |
| — senza claim sostitutivo | 2 |
| Righe V2 lette | 199 |
| Associazioni intervento V2 conservate nei parent | 159 |
| Parent nel ranking primario | 0 |
| Collisioni di ID | 0 |
| Blocker di migrazione | 3 |

### La divergenza dai 149 proiettati

`post_adjudication_schema_simulation.json` proiettava `resulting_claim_count:
149`, cioe' `147 - 13 + 15`. Quella proiezione assume che ognuno dei 134 record
non adjudicati porti esattamente un claim.

Tre non ne portano. `evidence:347`, `evidence:1846` e `evidence:1847` non hanno
alcun intervento — non nel loro statement e nemmeno nelle righe V2 da cui
vengono — e la loro direzione e' `prognostic` o `diagnostic`. I tre tipi di
claim del modello sono tutti tipi di intervento: nessuno puo' ospitare un record
che non afferma l'effetto di una terapia. Non sono nemmeno associazioni non
risolte, perche' un'associazione richiede un letterale di intervento a cui
riferirsi, e qui non ce n'e' nessuno.

Restano quindi parent con zero claim, con un blocker registrato in
`migration_blockers.jsonl`. Il conteggio derivato e' **146 = 15 + 131**, e la
differenza dalla proiezione e' esattamente il numero dei blocker.

I tre blocker non impediscono la promozione: non descrivono record persi, ma
record che non hanno mai affermato una terapia. La proiezione a 149 andra'
corretta a 146 quando l'adjudication verra' rivista, oppure i tre record andranno
rappresentati da un tipo di claim non terapeutico che oggi non esiste. E' una
decisione di modello, non di implementazione, e questa fase non la prende.

## I 13 gruppi adjudicati

L'adjudication congelata e' applicata alla lettera. I `claim_id` sono
ricalcolati con la formula e confrontati con quelli gia' emessi: una divergenza
solleva invece di passare inosservata. Tutti e 15 coincidono.

| Gruppo | Esito |
|---|---|
| `evidence:275` | 1 aggregate di classe (`EGFR tyrosine kinase inhibitor`), 2 unsupported, nessun claim atomico su erlotinib o gefitinib |
| `evidence:4759` | nessun claim, 2 unsupported, statement deprecato senza sostituto |
| `evidence:3811` | nessun claim, 3 unresolved, full text richiesto |
| `evidence:11240` | 1 regimen (erlotinib + ramucirumab, braccio sperimentale) e 1 atomic (erlotinib, braccio di controllo), con unita' di fonte e locator separati |
| `evidence:12131` | 1 regimen (amivantamab + lazertinib), nessun claim sui componenti |
| `evidence:12156` | 1 regimen, terminology review pendente |
| `evidence:1483`, `evidence:1484` | 1 atomic ciascuno, 1 unsupported ciascuno |
| `evidence:1851`, `evidence:1853` | 1 aggregate non separabile ciascuno, 1 unresolved ciascuno |
| `evidence:229`, `evidence:296` | 2 atomic ciascuno |
| `evidence:841` | 2 atomic, 1 unresolved |

## I 134 record non adjudicati

Il claim corrente e' portato avanti senza essere migliorato ne' peggiorato:

- `migration_origin = legacy_single_statement`;
- `review_status` invariato rispetto allo statement (`pending_verification`);
- `propagation_policy` invariata (`prototype_only`);
- `documentary_revalidation_completed = false`;
- nessuna source unit nuova: `source_unit_ids` e' vuoto;
- nessun locator inventato;
- `legacy_statement_ids` conserva il puntatore allo statement di origine.

L'identita' di questi claim richiede un `source_unit_id`, che per definizione non
esiste: nessuna revisione documentale li ha prodotti. Viene usato un token
esplicito, `LEGACY-NO-REVIEWED-SOURCE-UNIT:<statement_id>`, riconoscibile a vista
e registrato nella provenance. Inventare un identificativo che somigliasse a
un'unita' documentale avrebbe reso indistinguibile un claim revisionato da uno
che non lo e'.

## Deprecazione e backward compatibility

Nessuno statement operativo viene cancellato. La mappa in
`legacy_statement_deprecation_map.jsonl` copre tutti e 147 gli statement, e ogni
riga e' reversibile e conserva `statement_still_readable: true`.

| Stato | Statement |
|---|---|
| `replaced_by_atomic_claim` | 6 |
| `replaced_by_aggregate_claim` | 3 |
| `replaced_by_regimen_claim` | 2 |
| `deprecated_without_replacement` | 2 |
| `preserved_as_legacy_migrated_claim` | 134 |

Sono deprecati soltanto i 13 statement dei gruppi adjudicati. Il corpus
operativo continua a usarli tutti e 147.

I piani di rigenerazione — 15 link da creare, 13 da ritirare, 13 view da
rigenerare — sono descritti in
`qualification_link_regeneration_plan.jsonl` e
`qualified_view_regeneration_plan.jsonl` con `executed: false`. Descrivono cosa
accadrebbe alla promozione; questa fase non li esegue.

## Identita'

    claim_id = "CLM-" + sha256(
        graph_evidence_id | claim_type | canonical_intervention_or_regimen
        | biomarker | direction | polarity | source_unit_id
    )[:20]

Il separatore `|` e' esplicito e non puo' comparire dentro un campo: la
serializzazione solleva se ci provasse, perche' senza separatore `("ab", "c")` e
`("a", "bc")` produrrebbero lo stesso ID. La canonicalizzazione dei regimi ordina
i componenti, quindi l'identita' non dipende dall'ordine di scrittura. Gli alias
pending non vengono fusi: `bgj398` e `infigratinib` restano identita' distinte,
perche' fonderle renderebbe stabile un'equivalenza che nessuno ha verificato.

Parent e associazioni hanno spazi di ID separati (`GEP-`, `UNS-`, `UNR-`) e il
kind entra nel payload dell'hash, cosi' un parent non puo' essere scambiato per
un claim nemmeno per collisione. Su 305 identificatori generati le collisioni
sono zero.

## Integrita' operativa

Gli undici gruppi di artefatti operativi hanno hash identici prima e dopo la
fase: adjudication, migration specification, claim-type retrieval contract,
adapter corrente, qualification corpus 2.0, repository EvidenceStatement,
QualifiedEvidenceRetriever, configurazione di scoring, QualifiedEvidenceView,
output V2 congelati, gold bundle.

Nessun modulo operativo importa il package shadow, e questo e' verificato da un
test invece che promesso. Il gold non e' mai stato letto. Nessuna rete, nessun
Neo4j, nessun LLM.

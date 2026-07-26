# Specifica di migrazione adapter e corpus

`status = specified_not_applied`. E' una specifica: non e' stata applicata, l'adapter non
e' stato toccato, il corpus non e' stato rigenerato.

## graph evidence record: Nuovo GraphEvidenceRecord **(breaking)**

Sostituisce lo statement scalare come punto di arrivo dell'adapter V2. Conserva graph_evidence_id, record V2 originario, source identity, provenance, raw fields, adapter lineage, associazioni non materializzate e stato della review. Non porta intervention, direction o polarity come campi interrogabili: quei campi migrano sui claim. Non e' contato come therapy claim, non e' restituito come claim primario, non entra nelle metriche claim-level.

## claim schema: Schema dei claim **(breaking)**

Tre tipi tipizzati: atomic_intervention_claim, aggregate_intervention_claim, regimen_claim. Campi comuni: claim_id, claim_type, graph_evidence_parent, source_id, source_unit_id, locator, biomarker, disease_scope (esplicito, ammesso 'unknown'), direction, polarity, evidence_setting, support_level, review_state. Campi specifici: regimen_components per i regimi, aggregate_members e aggregate_kind e permits_member_specific_claims=false per gli aggregati, supporting_units per le unita' secondarie.

## parent child relationship: Relazione parent-child **(breaking)**

Ogni claim punta a un solo graph_evidence_parent; un parent porta da zero a N claim. Zero e' un esito legittimo: evidence:3811 e evidence:4759 restano senza claim. Il parent non e' un fallback del primo child e non viene restituito quando i claim sono zero.

## aggregate claim: Aggregate claim

Rappresenta un risultato condiviso fra farmaci, una classe farmacologica o un pannello non separabile. I membri sono i termini letterali della fonte. permits_member_specific_claims resta false: un aggregato non autorizza mai la derivazione di claim per singolo membro. Un aggregato puo' essere di classe (evidence:275) o su un insieme di inibitori (evidence:1851, evidence:1853).

## regimen claim: Regimen claim

I componenti sono canonicalizzati in ordine lessicografico e il risultato appartiene alla combinazione. Nessuna propagazione ai componenti. I componenti possono includere entita' descritte dalla fonte ma assenti dal grafo (pemetrexed in evidence:12156): la migrazione deve poterle creare. Un componente puo' avere un proprio claim atomico solo se poggia su una source_unit_id diversa da quella del regime.

## unsupported and unresolved: Associazioni unsupported e unresolved

Conservate sul parent, mai promosse a claim, mai esposte al retrieval primario, sempre auditabili. unsupported_association indica che la fonte non sostiene l'associazione; unresolved_association che il supporto non e' determinabile per abstract insufficiente, locator insufficiente, mapping pending o scope incerto. La distinzione va conservata: la prima e' una conclusione, la seconda una sospensione.

## id strategy: Strategia degli ID **(breaking)**

claim_id = SHA256(graph_evidence_id + claim_type + canonical_intervention_or_regimen + biomarker + direction + polarity + source_unit_id), primi 20 caratteri esadecimali con prefisso CLM-. Per i regimi la canonicalizzazione ordina i componenti, quindi l'ID non dipende dall'ordine di scrittura. I codici di sviluppo non vengono sostituiti dal nome generico nemmeno nella canonicalizzazione: altrimenti l'ID renderebbe stabile un'equivalenza non verificata.

## adapter v2 to parent: Adapter V2 verso parent **(breaking)**

L'adapter smette di promuovere il primo valore scalare dei campi multi-valore a intervento dello statement. Emette un GraphEvidenceRecord per record V2, con tutte le associazioni conservate e nessuna proposizione terapeutica. E' il punto in cui nascevano i quattro claim non sostenuti trovati dall'adjudication.

## adapter to claims: Adapter verso claim **(breaking)**

I claim non sono derivabili automaticamente dal record V2: nascono dalla revisione documentale, che fornisce source unit, locator, tipo e attribuzione. L'adapter li accetta come input revisionato e ne verifica le precondizioni di materializzazione, rifiutando quelli privi di locator sufficiente o costruiti su un mapping pending.

## provenance: Provenance

Ogni claim conserva graph_record_ids del parent, snapshot_fingerprint, extraction_action_id, e in aggiunta l'identita' della revisione che lo ha prodotto e dell'adjudication che lo ha approvato, con reason code. La catena adapter -> parent -> revisione -> adjudication -> claim deve essere ricostruibile in entrambe le direzioni.

## qualification link: Qualification link **(breaking)**

I link si spostano dallo statement al claim. I 13 link esistenti sui parent vanno ritirati e sostituiti da 15 link sui claim approvati. I parent senza claim non ricevono link.

## qualified evidence view: QualifiedEvidenceView **(breaking)**

La view espone claim, non parent. Deve poter rappresentare i tre tipi senza appiattirli: un regimen_claim non va reso come un elenco di componenti indipendenti, un aggregate_claim non va reso come il suo primo membro. Le associazioni unsupported e unresolved restano accessibili solo in modalita' audit.

## retrieval index: Indice di retrieval **(breaking)**

Indicizza i claim. I parent restano raggiungibili per provenienza ma non sono candidati primari. Cambia il numero di unita' indicizzate per i 13 gruppi: 13 statement diventano 15 claim, con due gruppi che non ne producono alcuno.

## scoring compatibility: Compatibilita' dello scoring **(breaking)**

Lo scoring attuale assume un intervento scalare per unita' indicizzata. Regimi e aggregati non lo hanno. Serve una regola di match esplicita per tipo di claim, decisa prima dell'implementazione e non ricavata dai risultati: quale sia va deciso in una fase dedicata, non qui.

## metric migration: Migrazione delle metriche **(breaking)**

Le metriche claim-level cambiano denominatore. Le misure prodotte prima della migrazione non sono direttamente confrontabili con quelle successive e vanno etichettate con la versione del corpus. Nessuna metrica di retrieval e' stata calcolata in questa fase e nessuna soglia e' stata ottimizzata.

## deprecation: Deprecazione degli statement esistenti **(breaking)**

I 13 statement operativi corrispondenti ai gruppi adjudicati vanno deprecati come claim, non cancellati: restano leggibili come record storici con un puntatore al parent che li sostituisce. Due di essi (evidence:275 ed evidence:4759) non hanno alcun claim sostitutivo e la deprecazione va motivata col reason code.

## backward compatibility: Backward compatibility **(breaking)**

Non c'e' compatibilita' all'indietro sul contratto di claim: un consumatore che si aspetta un intervento scalare per statement va aggiornato. E' garantita la compatibilita' di provenienza: ogni claim risale al proprio graph_evidence_id e ogni statement deprecato indica il parent. Va previsto un periodo in cui entrambe le rappresentazioni sono leggibili e solo la nuova e' interrogabile.

## corpus version bump: Version bump del corpus **(breaking)**

Cambio di schema maggiore: il corpus passa a una nuova versione con nuovo fingerprint. Gli artefatti che citano il fingerprint precedente vanno rigenerati o marcati come riferiti alla versione precedente.

## migration manifest: Migration manifest

La migrazione deve emettere un manifest con: conteggi prima e dopo, elenco degli statement deprecati con reason code, elenco dei claim creati con il rispettivo parent, link ritirati e creati, view rigenerate, fingerprint precedente e nuovo, e l'insieme delle decisioni di adjudication su cui si basa.

## rollback plan: Piano di rollback

La migrazione e' reversibile finche' gli statement deprecati restano leggibili e il manifest conserva la corrispondenza claim -> parent -> statement. Il rollback consiste nel ripristinare l'interrogabilita' degli statement deprecati e ritirare i claim creati; non richiede di ricostruire nulla dalla fonte. Il punto di non ritorno e' la rimozione fisica degli statement deprecati, che va rimandata oltre un ciclo di verifica completo.

## Esplicitamente fuori dalla specifica

- implementazione dell'adapter
- rigenerazione del corpus
- regole di scoring per tipo di claim
- politica di gerarchia fra claim
- qualunque metrica di retrieval

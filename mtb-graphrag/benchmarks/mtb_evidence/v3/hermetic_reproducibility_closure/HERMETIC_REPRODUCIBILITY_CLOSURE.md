# Chiusura di riproducibilita' ermetica

Fase `hermetic-reproducibility-closure/1.0`.

Il repository non era riproducibile da un checkout pulito. Questa fase lo rende
tale senza cambiare una riga di semantica di retrieval, e senza rigenerare un
solo artefatto storico.

## Il difetto

Per otto fasi gli audit hanno congelato l'integrita' di un sorgente con lo
sha256 dei suoi byte, misurati con `Path.read_text(encoding="utf-8").encode("utf-8")`
sul disco di una macchina Windows. `read_text` converte le fini riga secondo la
piattaforma: quello che veniva misurato era il risultato di una conversione
implicita, e nessuno lo aveva dichiarato. Git conservava la forma LF, il disco
mostrava CRLF, i due digest erano diversi, e nessun controllo confrontava mai
l'uno con l'altro — perche' ogni verifica leggeva il file dallo stesso disco che
aveva prodotto l'impronta.

Dodici artefatti di otto fasi chiuse promettono cosi' un'impronta che nessun
clone puo' riprodurre.

## Cosa non e' stato fatto, e perche'

**Non si e' adattato il codice all'artefatto.** La fase precedente aveva chiuso
il problema aggiungendo un `\r` a `qualified_retriever.py` — un carattere, su
`import json` — e dichiarando due eccezioni in `.gitattributes` per consegnare in
checkout una forma diversa da quella canonica. Il commit `33b92ec` reverte
entrambe le cose. Un artefatto congelato registra una misura del passato; non
impone una forma al presente. Cambiare cio' che il repository distribuisce per
non dover cambiare cio' che un artefatto afferma e' il verso sbagliato.

Quelle eccezioni erano anche incomplete per costruzione: sei degli otto sorgenti
stanno sotto `mtb-graphrag/benchmarks/`, che dal commit `63ed143` ha un
`.gitattributes` proprio con `* text eol=lf`. Un file annidato ha la precedenza,
quindi per quei sei un'eccezione scritta alla radice sarebbe stata una riga
morta. Una convenzione che copre due casi su otto non e' una convenzione.

**Non si sono rigenerati gli artefatti storici.** Tre dei dodici stanno nel
corpus promosso, che ogni fase dichiara congelato. Rigenerarli significherebbe
cancellare la traccia di cosa fu misurato davvero.

## Cosa e' stato fatto

`artifact_hash_policy/2.0` (`backend/pipeline/evidence/integrity/hash_policy.py`)
dichiara le tre cose che la convenzione implicita non diceva:

1. l'integrita' si misura su `read_bytes()`, mai su `read_text()`;
2. la forma canonica e' LF, e ha un nome (`normalization: "lf"`);
3. un CR isolato e' un errore, non una fine riga: viene rifiutato, non convertito
   in silenzio. Convertirlo darebbe la stessa impronta a due file diversi, cioe'
   toglierebbe a un'impronta l'unica cosa che deve fare.

`artifact_hash_erratum.json` registra, sorgente per sorgente, entrambe le forme:
`historical_raw_sha256` (cio' che un artefatto afferma) e `canonical_lf_sha256`
(cio' che un checkout pulito produce), con `reason_code`
`LEGACY_LINE_ENDING_DEPENDENT_HASH` e il blob da cui l'impronta storica si rifa'.
Tenere entrambe e' il punto: una sola costringerebbe a scegliere fra riscrivere
la storia e mentire sul presente.

## Perimetro

**8 sorgenti · 12 artefatti · 26 referenze.**

| sorgente | forma storica | artefatti |
|---|---|---|
| `backend/pipeline/evidence/qualification.py` | crlf | 4 |
| `backend/pipeline/evidence/qualified_retriever.py` | raw (blob superato `7c57d5ca`) | 8 |
| `v3/disease_hierarchy_policy/disease_match_contract.json` | crlf | 3 |
| `v3/disease_hierarchy_policy/disease_policy_modes.json` | crlf | 3 |
| `v3/disease_hierarchy_policy/disease_relation_definitions.json` | crlf | 3 |
| `v3/disease_hierarchy_policy/verified_alias_registry_snapshot.json` | crlf | 3 |
| `v3/first_review/FIRST_REVIEW_QUEUE.md` | crlf | 1 |
| `v3/first_review/first_review_queue.csv` | crlf | 1 |

L'elenco non e' scritto a mano. Lo produce
`benchmarks/mtb_evidence/evaluation/scripts/build_artifact_hash_erratum.py`,
che indicizza ogni blob dell'object database in tre forme — quindi anche le forme
storiche di un file, non solo quella corrente — e cerca i letterali a 64
esadecimali dentro ogni artefatto testuale tracciato. I binari sono esclusi:
per un `.xlsx` normalizzare le fini riga significa corromperlo, e l'impronta
corretta e' quella dei byte grezzi.

La differenza fra scoprire e ricordare non e' accademica. Le due costanti scritte
a mano che questo erratum sostituisce — `FROZEN` e `KNOWN_UNREPRODUCIBLE` in
`test_external_input_isolation.py` — coprivano **10 referenze su 26** e omettevano
due sorgenti interi (`verified_alias_registry_snapshot.json` e
`FIRST_REVIEW_QUEUE.md`). Nessuno se n'era accorto perche' nessun controllo
confrontava la lista con il repository.

## Cosa lo tiene vero

`backend/tests/test_artifact_hash_policy.py`:

- ogni `canonical_lf_sha256` uguaglia lo sha256 dei byte che un checkout pulito
  scriverebbe — blob piu' la conversione dichiarata in `.gitattributes`, mai
  l'albero di lavoro: e' esattamente la differenza fra i due che il difetto
  sfruttava;
- ogni `historical_raw_sha256` compare ancora verbatim in ciascun artefatto che
  lo dichiara, ed e' ancora rifacibile dal blob citato — prova che nessun
  artefatto e' stato riscritto;
- nessuna impronta canonica compare gia' negli artefatti: se un disallineamento
  venisse chiuso davvero, il test fallisce e chiede di togliere la voce, cosi'
  l'erratum non diventa un elenco di cose vere una volta sola;
- l'erratum coincide con cio' che una scansione da zero scopre, quindi non puo'
  restare indietro rispetto al repository;
- nessun sorgente operativo porta piu' un CR aggiunto per far tornare un hash.

## Il secondo erratum: provenance dei generatori

`generator_provenance_erratum/1.0` registra un fatto **diverso** da quello del
primo erratum, ed e' per questo che e' un file separato.

`artifact_hash_erratum` dice: *l'impronta di un sorgente fu presa in una forma di
byte che un checkout pulito non riproduce*. Il file e' lo stesso, cambia la forma.

`generator_provenance_erratum` dice: *un artefatto congelato registra l'impronta
del generatore che lo produsse, e quel generatore e' cambiato dopo*. Qui il file
e' proprio un altro, e nessuna normalizzazione lo riporta indietro.

### Il punto fisso che si sposta

Un manifest che dichiara `generator_sha256` registra l'impronta del file che lo
sta scrivendo. E' un auto-riferimento: modificare il generatore cambia quel
valore, e **nessuna** versione successiva puo' riprodurre cio' che una versione
precedente aveva scritto — non perche' produca artefatti diversi, ma perche' *e'*
un file diverso.

Due manifest lo dichiarano, e due generatori sono cambiati in questa fase quando
i loro `_sha` sono passati dall'erratum delle impronte legacy:

| artefatto | campo | convenzione | versione |
|---|---|---|---|
| `multi_intervention_adapter_review/review_manifest.json` | `generator_source_sha256` | byte grezzi | `multi-intervention-adapter-review/1.0` |
| `multi_intervention_source_review/review_manifest.json` | `generator_sha256` | testo canonico LF | `multi-intervention-source-review/1.0` |

Le due convenzioni non sono state uniformate: cambiare il modo in cui un
artefatto congelato e' stato misurato non lo renderebbe piu' vero.

### Tre nozioni, tre controlli

Il test unico che falliva ne confondeva tre, e le confondeva in un solo `assert`:

**Integrita' storica** — il manifest conserva ancora l'impronta del generatore
originale. E' il controllo che impedisce di «chiudere» il caso riscrivendo
l'artefatto congelato: se qualcuno aggiornasse il manifest all'impronta corrente,
qui fallirebbe.

**Integrita' corrente** — il generatore di oggi ha la propria impronta e la
scrive negli artefatti che produce adesso. Non basta constatare che le due
impronte differiscono: se il generatore lasciasse indietro un valore vecchio,
passerebbe per una divergenza legittima.

**Compatibilita'** — non e' obbligatorio che un generatore corrente riproduca
byte per byte un artefatto prodotto da una versione precedente. Qui il contratto
richiede tutto **tranne** l'auto-riferimento dichiarato: `non_reproducible_fields`
elenca la deroga, e tutto cio' che non e' elencato deve tornare.

### Perche' non e' una whitelist

`check_compatible` fallisce in due direzioni. Se un campo **non dichiarato**
diverge, la deroga non lo copre e il test lo dice. Se una deroga **smette di
coprire una divergenza**, e' una riga morta e il test chiede di toglierla —
perche' una deroga inerte nasconderebbe la prossima differenza vera.

Verificato con due prove: riscrivere il manifest storico all'impronta corrente
fa fallire due test; cambiare `source_count` nel manifest committato fa fallire
la compatibilita' nominando il campo.

Nessuno `skip`, nessun `xfail`, nessuna whitelist generica. Gli artefatti storici
non sono stati toccati.

## La matrice dei quattro ambienti

Misurata sul commit finale, con entrambi i runner. Gli ambienti 2, 3 e 4 non
hanno ne' il bundle gold ne' la cache degli abstract, e le due variabili
d'ambiente sono esplicitamente non impostate.

| ambiente | ingressi | unittest | pytest |
|---|---|---|---|
| working tree | presenti | 2606 OK, 5 skip | 2647 passati, 5 skip |
| worktree `--detach` | assenti | 2606, **15 failure**, 5 skip | 2647 passati, 15 failed |
| clone locale | assenti | 2606, **15 failure**, 5 skip | 2647 passati, 15 failed |
| `git archive` estratto | assenti | 2577, **18 failure**, 51 skip | 2601 passati, 18 failed |

I 2647 passati sono **identici** nei primi tre ambienti, con e senza gli
ingressi esterni: e' la prova che la suite core non li legge. L'archivio ne
conta meno perche' non ha storia git — i test che la interrogano si dichiarano
saltati, ed e' una differenza motivata, non un difetto.

I cinque skip residui del core sono tutti integrazioni opzionali
(`RUN_LLM_INTEGRATION`, `RUN_CLOUD_MODEL_INTEGRATION`, `MTB_ALLOW_NETWORK_TESTS`).
**Nessuno** per un ingresso esterno mancante.

## Cosa resta aperto

### Gli hash di albero congelati (difetto pre-esistente, aperto)

Quindici test falliscono in ogni checkout pulito, e fallivano gia' a `b6694ba`.
Non sono un effetto di questa fase: sono **lo stesso difetto un livello piu'
su**.

`sha256_tree` calcola l'hash di una directory come elenco ordinato di
`path:hash`. Gli hash di albero congelati furono misurati su un working tree in
cui 65 file sono CRLF sul disco — vi furono estratti prima che
`mtb-graphrag/benchmarks/.gitattributes` imponesse LF, dal commit `63ed143`, e
nessuno li ha piu' toccati da allora. Un checkout pulito li consegna in LF, e
l'hash di albero cambia. In forma LF i 65 file sono **identici**: non c'e'
nessuna differenza di contenuto.

Cinque test distinti, in quattro moduli:

    test_prototype_corpus_promotion_1_4  OperationalIntegrityTests
    test_pre_promotion_required_fixes_1_4 IntegrityTests
    test_pre_promotion_audit_1_3         IntegrityTests
    test_author_approval_23344087        TestBlinding, TestDeterminism

La chiusura naturale e' la stessa gia' applicata al livello dei file: un erratum
che registri l'impronta storica di albero accanto a quella canonica, con
`reason_code` `LEGACY_LINE_ENDING_DEPENDENT_TREE_HASH`, e `sha256_tree` che
misuri sotto `artifact_hash_policy/2.0`. Non e' stata fatta qui perche' il
perimetro dichiarato per questo turno chiude **esclusivamente** i tre failure
della suite gold, ed estenderlo sarebbe stata una decisione non richiesta.

### Le dodici impronte legacy

Restano non riproducibili **per costruzione**: e' cio' che significa registrarle
in un erratum invece di sanarle. Chiuderle davvero richiede di rigenerare gli
artefatti che le contengono, e quella e' una decisione scientifica sulle fasi,
non una manutenzione del repository.

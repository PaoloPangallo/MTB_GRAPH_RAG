Clinical gold e snapshot gold
=============================

Due oggetti, due domande
------------------------

Il **clinical gold** risponde a: *che cosa dovrebbe essere ricostruito?* Deriva da
fonti primarie, registri dei trial e annotazione umana. Non dipende dal grafo e non
cambia se il grafo cambia.

Lo **snapshot gold** risponde a: *che cosa di quello e' presente e raggiungibile in
questo grafo?* E' legato a un fingerprint preciso — oggi
`ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae` — e va
ricostruito ogni volta che lo snapshot cambia.

Tenerli separati serve a una cosa sola, ma decisiva: **attribuire ogni perdita al
passaggio che l'ha causata**. Una fonte clinica valida ma assente dal grafo abbassa
la copertura del Knowledge Graph; non abbassa il recall del retriever, che non puo'
recuperare cio' che non esiste. Se i due oggetti coincidessero, un grafo incompleto
verrebbe scambiato per un retriever mediocre, e nessun intervento sarebbe guidato dal
dato giusto.

I quattro stati di presenza
---------------------------

| Stato | Significato | Preteso dal retriever? |
| --- | --- | --- |
| `present` | c'e' ed e' raggiungibile dal traversal | si |
| `partially_present` | c'e' ma incompleto, o non raggiungibile dal profilo del caso | si, se raggiungibile |
| `absent` | non c'e' | no |
| `ambiguous` | c'e' qualcosa di correlato, ma un conflitto ne impedisce l'equiparazione | no |

Due stati soli — presente o assente — non basterebbero. I casi sotto mostrano perche'.

Che cosa dicono i quattro casi
------------------------------

### K1 — FGFR2, colangiocarcinoma intraepatico

**Fonte clinica valida, assente o non raggiungibile nel grafo.**

Il gold attende pemigatinib e futibatinib. Nello snapshot:

- **pemigatinib** e' raggiungibile: PMID 32203698 esiste come nodo `Publication` e
  l'evidenza 8173 lo collega al farmaco;
- **futibatinib** esiste come nodo `Drug`, ma **nessun percorso del caso vi arriva**.
  Il farmaco c'e', l'evidenza che lo collegherebbe al profilo FGFR2 fusion in iCCA no.
  Stato `partially_present`, `reachable_by_fixed_plan = false`;
- **PMID 36652354** (FOENIX-CCA2) e' assente in qualunque forma;
- **entrambi gli NCT** attesi sono assenti.

C'e' inoltre un conflitto di specificita': l'evidenza pemigatinib e' annotata su
`Cholangiolocellular Carcinoma`, non su colangiocarcinoma intraepatico. Sottotipo e
categoria non sono intercambiabili, quindi la claim K1-C1 risulta `ambiguous`, non
`present`.

Conseguenza pratica: un sistema che non nomina futibatinib **non sta sbagliando il
retrieval**. Sta riflettendo una lacuna del grafo. La copertura terapeutica di K1 e'
0.75, il recall del retriever su cio' che era raggiungibile puo' essere 1.0, e i due
numeri non si contraddicono.

### A2 — ALK G1202R

**PMID presenti soltanto come `citation_id`.**

Tutti e tre i PMID attesi — 27432227, 30892989, 29650534 — esistono nello snapshot,
ma **nessuno come nodo `Publication`**: compaiono solo dentro l'array
`Evidence.citation_id`.

E' una differenza reale, non formale. La fonte e' recuperabile: un traversal che
arriva all'evidenza vede la citazione. Ma non esiste un nodo bibliografico da cui
partire, non c'e' `citation_text`, non c'e' anno, e una query che cercasse
`Publication` per PMID non troverebbe nulla. Chiamarli semplicemente "presenti"
nasconderebbe che il grafo li rappresenta a meta'; chiamarli "assenti" sarebbe falso.
Da qui lo stato `partially_present` con `missing_fields = ["publication_node"]`.

Il caso mostra anche la separazione fra mutazione singola e composta. Dei tre profili
molecolari che contengono G1202R, `ALK G1202R AND v::ALK Fusion` e' una mutazione
singola nel contesto di una fusione ALK, mentre `EML4::ALK Fusion AND ALK G1202R AND
ALK I1171N AND ALK L1196M` e' composta. Restano in bucket separati e non vengono mai
fusi: rispetto a lorlatinib hanno implicazioni opposte.

### C1 — EGFR L858R, prima linea avanzata

**Fonti non applicabili presenti, fonte applicabile assente.**

E' il caso piu' istruttivo, e il risultato e' controintuitivo:

| Fonte | Applicabilita' secondo il gold | Presenza nello snapshot |
| --- | --- | --- |
| FLAURA (29151359, NCT02296125) | **compatible** | PMID **assente**, NCT **assente** |
| ADAURA (32955177, NCT02511106) | not_compatible (adiuvante) | PMID e NCT **presenti** |
| AURA3 (27959700, NCT02151981) | not_compatible (T790M) | PMID presente, NCT assente |

Il grafo copre bene proprio i contesti che il caso deve **escludere**, e non copre
quello su cui la risposta corretta si fonda.

Un sistema che si limitasse a recuperare cio' che trova produrrebbe un report
plausibile e clinicamente sbagliato: due studi reali, correttamente citati, su
popolazioni che non sono quella del paziente. La risposta corretta non e' eliminarli
— sono fonti valide — ma **conservarli e qualificarli**. E' questa la ragione per cui
`applicability` e' misurata separatamente da `documentary_status`, e per cui esistono
`compatible_overstatement_rate` (dichiarare applicabile cio' che non lo e') e
`not_compatible_leakage_rate` (riportarlo senza dire che non lo e').

Nota sul caso: la domanda di C1 nomina esplicitamente osimertinib. E' input clinico
legittimo, non contaminazione, ma significa che il recall sulla terapia di C1 non
misura la capacita' di recuperarla. `leakage_overlap` lo dichiara.

### N1 — RMI2

**Vero negativo dello snapshot.**

Il nodo `Gene` RMI2 esiste (entrez 116028, alias BLAP18, C16orf75, MGC24665) ma non
ha **alcuna relazione di alcun tipo**: zero varianti, zero profili, zero evidenze,
zero interazioni farmacologiche, zero trial.

Il gold non afferma che nessuna evidenza esista al mondo. Afferma che nello snapshot
congelato non e' determinabile, ed e' una tesi verificabile: la prova negativa e'
archiviata in `negative_path_proof.json` con query, parametri, risultato vuoto,
conteggio, fingerprint e timestamp.

Un dettaglio che vale come avvertimento: il nodo porta la proprieta'
`categories: ["CLINICALLY ACTIONABLE", "DNA REPAIR"]` pur non avendo alcun percorso
terapeutico. Qualunque euristica che usasse quella proprieta' come segnale di
azionabilita' produrrebbe un falso positivo su questo caso.

Come si ricostruisce
--------------------

```bash
cd mtb-graphrag
PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/build_snapshot_gold.py
```

Input: il gold pilota e gli artefatti dell'audit del grafo. Output: `clinical_gold_v1.jsonl`,
`snapshot_gold_<fingerprint>.jsonl`, `clinical_snapshot_mapping.jsonl` e un report.

Due garanzie applicate a ogni build:

1. **`verify_no_loss`** confronta claim, fonti e identificatori del pilota con quelli
   del clinical gold e fallisce la build se qualcosa sparisce nella conversione.
2. **Gli emendamenti proposti dall'audit non vengono applicati.** Le 9 righe di
   `proposed_gold_amendments.jsonl` vengono lette solo per essere contate. Applicarle
   automaticamente lascerebbe che lo stato del grafo riscriva la verita' clinica, che
   e' l'inversione che questa separazione esiste per impedire.

Quando rifare lo snapshot gold
------------------------------

Ogni volta che il fingerprint cambia. Il clinical gold **non** va rifatto in
quell'occasione: cambia il grafo, non la letteratura. Se cambia anche il clinical
gold, e' perche' un revisore umano ha deciso qualcosa, e la modifica passa dalla
seconda revisione indipendente, non da uno script.

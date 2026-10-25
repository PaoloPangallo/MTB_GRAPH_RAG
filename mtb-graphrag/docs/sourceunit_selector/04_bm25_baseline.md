# BM25 come baseline seria

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatti: `baseline_first_k.json`, `baseline_bm25.json`.

## 1. Perché una baseline forte

Il rischio di questa fase non è costruire un componente che non funziona: è
costruirne uno complicato quando ne bastava uno semplice. §28 lo dice
esplicitamente — se BM25 puro pareggia, vince BM25.

## 2. Implementazione

Okapi BM25 con parametri standard, `k1 = 1.5`, `b = 0.75`. Non tarati: cambiarli
per guadagnare punti su 25 bundle sarebbe adattarsi al set di valutazione.

Il corpus dell'IDF è **il documento in esame**, non l'intera letteratura. La
domanda giusta quando si cerca il passaggio da citare è quanto un termine sia
raro *in questo articolo*.

La query è costruita esclusivamente dalla GCA: token di alterazioni, geni,
farmaci e malattia. Nessun altro ingresso.

## 3. Le tre strategie confrontate

| Strategia | Cosa fa |
|---|---|
| `baseline_first_k` | le prime K unità nell'ordine del parser (BASELINE A e B) |
| `baseline_bm25` | BM25 puro, nessuna feature clinica, nessun prior (BASELINE C) |
| `feature_selector` | BM25 + bonus clinici + prior strutturale + guardia di contesto |

`baseline_first_k` copre insieme «prime K unità» e «titolo + introduzione»:
nell'ordine del parser le prime unità di un full text **sono** titolo e
introduzione. Tenerle separate avrebbe prodotto due colonne identiche.

## 4. Risultati aggregati (25 bundle)

| Strategia | HitRate@3 | HitRate@5 | HitRate@10 | Recall@5 | Recall@10 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| first-k | 0.800 | 0.800 | 0.880 | 0.627 | 0.753 | 0.604 |
| BM25 puro | 0.880 | 0.920 | 1.000 | 0.827 | 0.900 | 0.817 |
| **feature selector** | **1.000** | **1.000** | **1.000** | **0.920** | **0.943** | **0.913** |

## 5. Il numero aggregato inganna

`first-k` a 0.800 sembra una baseline già buona. Non lo è: sedici dei
venticinque documenti hanno meno di venti unità, e lì prendere le prime tre
significa quasi sempre prenderle giuste.

Stratificando per dimensione del documento:

| Fascia | Bundle | selector | BM25 | first-k |
|---|---:|---:|---:|---:|
| piccolo (<20 unità) | 16 | 16/16 | 16/16 | 15/16 |
| medio (20-99) | 2 | 2/2 | 1/2 | 2/2 |
| **grande (100+)** | **7** | **7/7** | 5/7 | **3/7** |

Sui sette documenti grandi — i full text PMC, cioè il materiale con più valore
probatorio — `first-k` trova il gold nei primi tre in **tre casi su sette**. BM25
in cinque. Il feature selector in sette.

## 6. Le feature cliniche servono? (§28)

Sì, e in modo misurabile: BM25 puro passa da 5/7 a 7/7 sui documenti grandi, e
il MRR sale da 0.817 a 0.913. La differenza sta nei bonus per gene, alterazione
e farmaco e nel prior che penalizza le intestazioni di sezione — che BM25 da
solo, essendo cieco al tipo di unità, non distingue da un paragrafo.

Il metodo più complesso vince, ma di poco e per ragioni comprensibili. Se la
differenza fosse stata nulla, la conclusione corretta sarebbe stata tenere BM25.

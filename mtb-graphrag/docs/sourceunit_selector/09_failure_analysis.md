# Analisi dei fallimenti e dei limiti

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatti: `failure_cases.csv`, `negative_control.json`, `retrieval_metrics.json`.

## 1. Fallimenti di retrieval

`failure_cases.csv` è **vuoto**: su 25 bundle non esiste un caso in cui il
selector non porti almeno una gold nei primi cinque.

I 7 gold mancati a K=5 si distribuiscono su bundle che comunque hanno altre gold
in cima. Di questi 7, tre sono disaccordi di granularità (testo coincidente,
taglio diverso). I mancati di contenuto sono **4 su 76**.

## 2. Il controllo negativo — il limite più importante

Il contratto del selector è ordinare *dentro* un documento già collegato alla
candidate dalla provenance della GCA. Ma vale la pena chiedersi se il punteggio
possa fare anche altro: distinguere un documento pertinente da uno che non lo è.

Incrociando ogni candidate con ogni documento (400 coppie, di cui 25 realmente
collegate):

| | coppie collegate | coppie non collegate |
|---|---:|---:|
| n | 25 | 375 |
| top-score mediano | **7.08** | **0.00** |
| top-score minimo / p95 | 2.01 | 6.08 |
| `NO_RELEVANT_SOURCE_UNIT` | — | 65.9% |

In aggregato la separazione è netta. Ma **il 22.9% delle coppie non collegate
ottiene un punteggio pari o superiore al minimo delle collegate**, e il massimo
delle non collegate (12.32) supera la mediana delle collegate.

Conclusione: il punteggio **non è utilizzabile come gate di rilevanza
documentale**. Se una futura architettura volesse usarlo anche per decidere
*quale* documento valga la pena leggere, servirebbe un criterio diverso — questo
produrrebbe falsi positivi in un caso su quattro.

Dentro il proprio contratto il selector funziona; fuori, no. È bene saperlo
prima di riusarlo.

## 3. Limiti metodologici

| Limite | Perché conta |
|---|---|
| **25 bundle** | Numerosità troppo bassa per una stima stabile; nessuna divisione train/test possibile |
| **Gold = scelta del pilot** | Riprodurlo misura anche l'aderenza a una preferenza di granularità, non solo la rilevanza |
| **Pesi scelti dopo aver visto il corpus** | Il prior è argomentato strutturalmente, ma l'adattamento implicito non si può escludere |
| **Documenti live = riscaricati, non nuovi** | Nessuna prova su articoli mai visti, dove peraltro non esisterebbe gold |
| **Campione Gemma n=8** | Le differenze osservate (nulle) hanno ampio intervallo di incertezza |
| **Un solo dominio** | Oncologia molecolare, con feature molto specifiche (varianti puntuali) |

## 4. Casi che il corpus non contiene

Non è stato possibile testare:

- un documento in cui l'alterazione compaia **solo** in tabella, perché nel
  corpus le `TABLE_CELL` non sono mai gold (il comportamento è verificato da un
  test sintetico, non su dati reali);
- una candidate con più farmaci in cui il selector debba discriminare fra loro;
- documenti in lingua diversa dall'inglese;
- articoli con testo corretto o ritirato dopo la pubblicazione.

## 5. Cosa servirebbe per superare questi limiti

1. Un secondo corpus annotato, costruito **indipendentemente** dal pilot, per
   misurare senza riprodurre la preferenza di granularità.
2. Annotazione di rilevanza a livello di passaggio su documenti nuovi, così da
   valutare senza dipendere dai bundle.
3. Un criterio separato per la rilevanza documentale, se si vuole usare il
   selector anche in quel ruolo.

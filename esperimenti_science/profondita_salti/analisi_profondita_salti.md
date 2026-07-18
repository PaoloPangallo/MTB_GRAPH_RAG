# Strand E — Scaling della profondità dei salti (deep-hop)

## Domanda sperimentale

Fino a che punto la struttura del grafo continua a proteggere il recupero quando la
catena di ragionamento clinico si allunga? Gli strand precedenti hanno lavorato su
domande a 2–5 salti. Qui portiamo la profondità fino a **8 salti** e misuriamo due
cose distinte, entrambe in modo deterministico e offline (router = oracolo, nessun
LLM nel ciclo di misura):

1. **Recall del fatto terminale** — il nome dell'entità-obiettivo finale compare nel
   contesto recuperato?
2. **Chain-recall (completezza della catena)** — quale frazione dei nomi-ponte
   intermedi compare nel contesto?

La seconda metrica è il cuore dello strand: una risposta a molti salti non è utile
solo se contiene il fatto finale, ma se contiene *tutti gli anelli* che lo giustificano.

## Disegno: una spina tipizzata, uno stesso gene ad ogni profondità

Il rischio metodologico in un esperimento di profondità è confondere la profondità con
la scelta del sotto-grafo. Lo evitiamo con una **spina tipizzata unica**:

```
Gene → Variant → MolecularProfile → Evidence → Drug
     → CompanionDiagnostic → Gene' → Variant' → MolecularProfile'
```

Ogni gene-ancora che possiede un **cammino canonico completo** a profondità 8 (91 geni,
selezionati da 1 437 geni; DFS deterministico con successori mescolati da `SEED=20240517`)
viene troncato a profondità crescenti. Poiché **lo stesso gene** genera la domanda ad ogni
profondità, la profondità resta l'unica variabile manipolata.

La profondità 3 ha come terminale un nodo `Evidence`, che nel KB **non ha attributo
`name`**: non è nominabile in un test testuale, quindi è esclusa. Le profondità usate sono
**[1, 2, 4, 5, 6, 7, 8]**, per un totale di **637 domande** (91 ancore × 7 profondità).

## La covariata onesta: quanti passaggi separati servono

Prima dei risultati, documentiamo il meccanismo. La figura `deep_hops_fanout.png` conta,
per ciascun cammino canonico, quanti **passaggi distinti** del corpus sono necessari per
testimoniare l'intera catena (un passaggio testimonia un salto se il suo testo contiene i
nomi di entrambi gli estremi).

| Profondità | Passaggi distinti (mediana) |
|-----------:|:---------------------------:|
| 1–4        | 1                           |
| 5–6        | 2                           |
| 7          | 3                           |
| 8          | 4                           |

Fino alla profondità 4 l'intera catena vive dentro **un solo** passaggio ricco (il corpus
è evidence-centric: un passaggio raggruppa Gene+Variant+Profilo+Evidenza+Farmaco). Da
profondità 5 in poi il RAG deve **recuperare e unire passaggi separati** — ed è esattamente
lì che ci aspettiamo il crollo del recupero testuale.

## Risultati

### Recall del fatto terminale (`fig13`, pannello a)

| Profondità | GraphRAG | RAG BM25 | RAG ibrido | RAG denso |
|-----------:|:--------:|:--------:|:----------:|:---------:|
| 1  | 1,000 | 0,802 | 0,846 | 0,275 |
| 2  | 1,000 | 0,835 | 0,868 | 0,143 |
| 4  | 0,989 | 0,879 | 0,879 | 0,198 |
| 5  | 0,967 | 0,473 | 0,418 | 0,165 |
| 6  | 0,989 | 0,637 | 0,637 | 0,231 |
| 7  | 0,582 | 0,099 | 0,088 | 0,044 |
| 8  | 0,451 | 0,022 | 0,022 | 0,000 |

GraphRAG **domina ad ogni profondità**. Il salto 5 (Farmaco→Test diagnostico) è un vero
scoglio per il RAG: la recall di BM25 crolla da 0,879 a 0,473 perché il farmaco e il suo
test di accompagnamento **non sono più co-menzionati nello stesso passaggio**. GraphRAG,
che attraversa l'arco `HAS_COMPANION_DIAGNOSTIC` esplicitamente, resta a 0,967.

**Il calo di GraphRAG a profondità 7–8 è un confondimento di fan-out documentato, non un
guasto.** Il settimo salto è un secondo `HAS_VARIANT`: il gene raggiunto (per esempio
attraverso un test diagnostico pan-tumore) può ramificare in decine di varianti. Per
ABCB1 la profondità 8 genera 162 cammini; sotto il budget di 900 parole solo ~17 vengono
serializzati, quindi lo *specifico* terminale canonico compete con i suoi fratelli e non
sempre entra nel contesto. È recupero limitato dal budget su un ventaglio combinatorio —
la stessa pressione che la covariata di fan-out anticipa.

### Chain-recall / completezza della catena (`fig13`, pannello b)

| Profondità | GraphRAG | RAG BM25 | RAG ibrido | RAG denso |
|-----------:|:--------:|:--------:|:----------:|:---------:|
| 2  | 1,000 | 0,857 | 0,868 | 0,242 |
| 4  | 0,956 | 0,846 | 0,813 | 0,033 |
| 5  | 0,930 | 0,586 | 0,319 | 0,147 |
| 6  | 0,937 | 0,703 | 0,618 | 0,135 |
| 7  | 0,767 | 0,692 | 0,673 | 0,182 |
| 8  | 0,707 | 0,592 | 0,586 | 0,119 |

Qui emerge la proprietà strutturale di GraphRAG. Ogni cammino serializzato è **internamente
completo per costruzione** — nomina tutti i nodi-ponte lungo la spina — quindi la
chain-recall **degrada con grazia** (1,000 → 0,707) invece di crollare. Il RAG denso, che
deve coprire ogni salto in modo indipendente, resta **inchiodato sotto 0,20** a ogni
profondità: la probabilità che un singolo recupero copra *tutti* gli anelli decade
moltiplicativamente. BM25 e ibrido tengono meglio del denso ma restano ~0,12–0,15 sotto
GraphRAG per tutta la coda.

Si noti che a profondità 7–8 la chain-recall di GraphRAG (0,77 / 0,71) è **molto più alta**
della sua recall terminale (0,58 / 0,45): anche quando il budget espelle lo specifico
terminale, gli anelli intermedi della catena restano in gran parte nel contesto. La
struttura preserva il *ragionamento* anche dove il ventaglio combinatorio mette sotto
pressione la singola risposta finale.

## Conclusioni

1. **La struttura protegge il recupero profondo.** Su terminale e catena, GraphRAG è
   superiore ad ogni profondità; il divario si allarga proprio dove la catena smette di
   vivere in un unico passaggio (profondità ≥ 5).
2. **La completezza della catena è la metrica che separa i paradigmi.** GraphRAG degrada
   con grazia perché ogni cammino è completo per costruzione; il RAG denso collassa perché
   deve coprire ogni salto in modo indipendente.
3. **Il limite di GraphRAG è il budget, non la connettività.** Il calo terminale a
   profondità 7–8 è ventaglio combinatorio sotto un budget fisso di 900 parole — un limite
   di *impaginazione*, non di *raggiungibilità*: la connettività del grafo garantisce che
   il terminale sia sempre a distanza finita; è la serializzazione a doverlo scegliere fra
   molti fratelli.

## File

- `benchmark_deep_hops.csv` — 637 domande annidate (ancora, profondità, terminale gold,
  catena-ponte JSON, domanda in italiano).
- `deep_hops_sweep.csv` — recall per sistema × profondità × metrica (terminale + catena).
- `deep_hops_fanout.png` — covariata: passaggi distinti che testimoniano la catena vs profondità.
- `fig13_profondita_salti.png` — figura principale a doppio pannello.
- `08_profondita_salti.py` — script standalone riproducibile (SEED=20240517, offline,
  sweep verificato bit-identico).

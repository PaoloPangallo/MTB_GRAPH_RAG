# Efficienza di contesto: recupero dei fatti al variare del budget

## Domanda

Il confronto principale della tesi fissa il budget di contesto a 900 parole
per tutti i sistemi. A quel budget il GraphRAG usa in media ~36 parole per
raggiungere una recall dei fatti-gold pari a 1,00, mentre il RAG testuale ne
consuma ~900 per fermarsi molto più in basso. Un revisore può obiettare:
*e se il divario fosse solo un artefatto del budget scelto? Concedendo al RAG
più contesto, il divario si chiude?* Questo esperimento risponde variando il
budget su 12 livelli, da 100 a 2400 parole.

## Metrica e metodo

Misuro la **recall dei fatti-gold effettivamente presenti nel contesto**
assemblato — cioè quanta parte delle entità della risposta corretta il
sistema riesce a mettere sotto gli occhi del lettore. È una metrica
deterministica che non richiede il modello lettore, quindi lo sweep è
interamente offline e riproducibile. Per ogni livello di budget il contesto
è assemblato con la stessa procedura `pack_context` del sistema principale
(accumulo di passaggi finché il budget è saturo). Il GraphRAG entra come
riferimento: il suo contesto è già minimo (~36 parole) e insensibile al
budget.

## Risultati

**Recall dei fatti-gold vs budget di contesto:**

| budget (parole) | GraphRAG | RAG BM25 | RAG ibrido | RAG denso |
|----------------:|:--------:|:--------:|:----------:|:---------:|
| 100  | 1,00 | 0,54 | 0,56 | 0,14 |
| 300  | 1,00 | 0,71 | 0,73 | 0,22 |
| 900 (budget tesi) | 1,00 | 0,84 | 0,83 | 0,29 |
| 1800 | 1,00 | 0,89 | 0,88 | 0,36 |
| 2400 | 1,00 | 0,93 | 0,89 | 0,39 |

**Efficienza — parole di contesto necessarie per raggiungere una soglia di recall:**

| soglia | GraphRAG | RAG BM25 | RAG ibrido | RAG denso |
|:------:|:--------:|:--------:|:----------:|:---------:|
| ≥60% | 36 | 144 | 112 | mai |
| ≥70% | 36 | 251 | 226 | mai |
| ≥80% | 36 | 575 | 690 | mai |

## Interpretazione

1. **Il vantaggio del GraphRAG non dipende dal budget scelto.** Anche
   concedendo al RAG testuale 2400 parole (≈2,7× il budget della tesi),
   BM25 arriva a 0,93 e l'ibrido satura intorno a 0,89: nessuno dei due
   raggiunge il tetto del grafo (1,00 con ~36 parole). Per la soglia di
   recall ≥80% il GraphRAG è circa **16× più efficiente** di BM25 e **19×**
   dell'ibrido.

2. **Il RAG denso è limitato dall'encoder, non dal contesto.** La sua recall
   passa da 0,14 a soli 0,39 lungo tutto lo sweep e non raggiunge mai
   neppure il 60%. Allargare il budget non lo aiuta: il collo di bottiglia è
   l'encoder generico (`all-MiniLM-L6-v2`), non lo spazio di contesto. Questo
   motiva, come esperimento distinto, la sostituzione con un encoder
   biomedico dedicato (MedCPT, PubMedBERT, SapBERT).

3. **Per BM25 e ibrido il collo di bottiglia si sdoppia.** Già a 900 parole
   la recall di retrieval (~0,83) supera la F1 end-to-end del lettore
   (~0,67 nella run principale): oltre un certo budget il limite non è più
   il recupero, ma il ragionamento del lettore su un contesto testuale
   lungo e rumoroso. Aggiungere parole recupera qualche fatto in più ma
   introduce anche più distrattori.

## Conclusione

La curva di degrado conferma che l'efficienza di contesto del GraphRAG è una
proprietà **strutturale**, non un effetto della parametrizzazione. Il grafo
consegna al lettore esattamente i fatti-ponte richiesti in poche decine di
parole; il RAG testuale deve inondare il lettore di contesto per avvicinarsi,
senza mai raggiungere lo stesso tetto di recall.

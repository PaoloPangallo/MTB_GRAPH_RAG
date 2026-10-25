# La domanda

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**
**Sonda sperimentale. Nessuna modifica architetturale.**

## 1. Cosa vogliamo sapere

> Una candidate recuperata dal grafo contiene abbastanza provenance da
> permettere al sistema, senza intervento umano, di arrivare al documento
> scientifico originale tramite API ufficiale e fornire a Gemma testo
> utilizzabile?

Detto in termini di prodotto: un clinico potrà mai usare questo sistema senza
sapere che cosa sia un PMID?

## 2. Perché non è una domanda banale

Il runtime oggi funziona perché la cache documentale contiene già i 40 documenti
del pilot, e il manifest congelato dice dove trovarli. Su un caso il cui
documento non fosse in cache, lo stage 6 produce `DOCUMENT_UNAVAILABLE` e si
ferma — deliberatamente, perché non deve inventare né ripiegare.

Una futura architettura operativa vorrebbe invece:

```
CACHE HIT   -> usa il documento locale
CACHE MISS  -> recupera dalla fonte ufficiale, materializza, parsa, prosegue
```

Questo è possibile solo se l'identificatore del documento è **derivabile dalla
macchina**. Se dovesse arrivare da una tabella di mapping esterna, da un
inserimento manuale o da una ricerca semantica sul web, l'automazione sarebbe
impossibile — o peggio, sarebbe possibile ma non tracciabile.

## 3. L'ostacolo concreto

Ispezionando le candidate reali emerge subito il problema:

> **La GraphCandidateAssertion porta soltanto PMID.** Nessun PMCID compare mai
> nella sua provenance.

Eppure sette dei venticinque bundle congelati citano documenti `pmcid:`, cioè
full text PMC. Da dove viene quel PMCID?

Se fosse conoscenza esterna al sistema, la risposta alla domanda sperimentale
sarebbe no. La sonda verifica l'ipotesi alternativa: che sia **PubMed stessa** a
dichiararlo, e che la catena `PMID → PubMed → PMCID → PMC full text` sia
percorribile per intero senza un essere umano.

## 4. Disciplina della prova

| Regola | Motivo |
|---|---|
| L'identificatore si legge **solo** da `candidate["document_identifiers"]` | Usare il `document_id` del bundle congelato sarebbe leggere la risposta già scritta |
| I documenti si riscaricano in directory temporanee | La cache reale non è né sorgente né bersaglio del test |
| Nessun documento alternativo se la fonte nega | Sostituire un paper con un altro è fabbricare evidenza |
| Nessuna ricerca semantica libera sul web | Il closed set è definito dalla provenance, non dalla rilevanza percepita |
| Il contratto con il modello resta QUOTE / ABSTAIN | Al modello non si chiedono raccomandazioni |

## 5. Cosa questa sonda non dimostra

Non accuratezza clinica. Non superiorità rispetto a un medico. Non completezza
della letteratura. Non aggiornamento del grafo. Non integrazione OncoKB. Non
production readiness.

Solo se il document grounding sia **tecnicamente** automatizzabile a partire
dalla provenance della candidate.

# Riscontri per i chiarimenti didattici

## Identità e normalizzazione

`terminology/case_resolution.py` conserva valori originali e stati di risoluzione; risolve il gene prima della variante e mantiene il contesto residuo della malattia. `retrieval/normalization.py` applica regole conservative alle forme lessicali e molecolari riconosciute. I tre esempi della pagina derivano dai riscontri già conservati in `esempi.json`: melanoma con contesto metastatico, coppia BRAF–V600K e intervento combinato non risolto come identità unica.

## Confronto semantico

`orchestrator.py` condiziona il confronto alla famiglia evidenza–farmaco, all'osservazione ammessa e alla struttura superata. `enrichment/semantic_alignment.py` passa relazione strutturata e testo con contesto al modello separato, senza il giudizio del Reader. `semantic_contract.py` verifica schema, passaggi letterali e dimensioni richieste dalle regole di ammissione. Non viene attribuita una chiamata al confronto aggiuntivo agli esempi di altre famiglie.

## Presentazione

`narrative/controlled.py` valida identità, varianti consentite, ordine e copertura; ricostruisce poi il contenuto atteso e confronta i campi autorevoli. `controlled_narrator.py` prepara un'alternativa deterministica se il piano del modello non è utilizzabile. `stage_runner.py` verifica separatamente l'alternativa: non modifica l'esito del modello e non conta come suo successo. `presentation.py` non allega prosa non verificata e mantiene la vista strutturata del dossier.

L'accettazione riguarda la fedeltà della presentazione, non la validità clinica del dossier o della terapia. Le alterazioni di eleggibilità o provenienza usate per spiegare il rifiuto sono esempi didattici, non risultati osservati nell'archivio. Le configurazioni sperimentali che bypassano la verifica non sono rappresentate come percorso predefinito.

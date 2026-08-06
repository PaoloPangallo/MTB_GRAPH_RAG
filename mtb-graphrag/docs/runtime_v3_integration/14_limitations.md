# 14 — Limitazioni

## Il rilevatore di istruzioni di controllo è una lista di pattern

Copre le forme del benchmark congelato: sovrascrittura delle istruzioni, cambio
di ruolo, esfiltrazione del prompt, raccomandazione imposta, fabbricazione
imposta, imposizione di valori di campo. **Non risolve universalmente la prompt
injection** e questo lavoro non lo afferma.

Una formulazione nuova non riconosciuta lascia passare la menzione, che può
ancora essere rifiutata dal verifier semantico per tipo, ruolo o asserzione —
ma non con il motivo corretto. Il rilevatore è deliberatamente conservativo: un
falso positivo scarterebbe contenuto clinico legittimo, che è il danno peggiore.

## Il rilevatore di contraddizioni copre sei forme

Entità insieme asserita e negata, stato genico mutuamente esclusivo, test
negativo con alterazione specifica, malattie primarie incompatibili, storia
terapeutica contraddittoria, istruzione che nega la domanda. Le sei coprono il
benchmark; una contraddizione di forma diversa non viene rilevata.

Due falsi positivi trovati e corretti durante lo sviluppo mostrano quanto il
margine sia stretto: la negazione che attraversava i confini di frase rendeva
negata la malattia in «Lung adenocarcinoma. EGFR testing was negative.», e
`wild-type` contato come alterazione positiva rendeva contraddittorio ogni
`KRAS wild-type`.

## Il lessico oncologico è una lista chiusa

`mentions_oncology()` usa 22 termini. Una neoplasia denominata fuori da quel
lessico non produrrebbe un ancoraggio, e il caso finirebbe in
`INSUFFICIENT_ONCOLOGY_CONTEXT` o `OUT_OF_SCOPE`. È un **falso negativo
conservativo**: rifiuta invece di ammettere, ma resta un limite reale.

Lo stesso vale per il lessico dei sintomi, che distingue
`NON_ACTIONABLE_MEDICAL_INPUT` da `OUT_OF_SCOPE`.

## La riesecuzione RQ4 riusa gli output del parser

Il parser non è cambiato e riusarli isola l'effetto dei nuovi stage. Ma per i 9
casi in cui il modello non ha prodotto una tool call conforme, il risultato è
ancora determinato dal comportamento del modello: il gate li classifica
`INVALID_INPUT`, che è corretto, ma non dimostra come li tratterebbe se il
modello avesse risposto.

## Il percorso end-to-end fino al dossier non è stato eseguito con v3

L'integrazione arriva a `CandidateRuntimeAdmission`. La separazione dei rami nel
dossier (positivo / negativo / neutro / polarità ignota / regime irrisolto /
alterazione parziale) è **definita ma non esercitata** su dati reali.

## Il ponte dei bundle non è validato caso per caso

Corretto per costruzione — usa il mapping di migrazione — ma associa il bundle di
una candidate a farmaco singolo all'unità di regime che la contiene. Nessuno ha
verificato che il documento sia ancora appropriato per l'unità.

## Il matching dell'intervento resta una sottostringa

`evaluate_intervention` confronta il target verificato con i nomi dei componenti
per sottostringa bidirezionale, come faceva v2. Nessun resolver terminologico è
stato introdotto: `BGJ398` e `infigratinib` restano termini distinti
(`KNOWN_DRUG_SYNONYM_GAP`).

## Il gate non usa `alteration_mentions` per il matching composto

`_case_alterations` accoppia geni e alterazioni **per posizione**. Se il parser
emette 2 geni e 1 alterazione, l'accoppiamento è arbitrario. Il caso non compare
nel benchmark, ma la struttura lo permette.

## Flakiness preesistente della suite frontend

In esecuzione parallela completa 2–3 test falliscono in modo non deterministico,
sia prima sia dopo queste modifiche. Con `--no-file-parallelism` passano tutti e
195. Non è introdotta da questo lavoro, ma non è stata risolta.

## Nessuna misura di impatto clinico

Nulla in questo lavoro dimostra che i dossier prodotti siano clinicamente
migliori. Le metriche riguardano il **routing** e l'**ammissione**, non la
qualità dell'evidenza presentata a un medico.

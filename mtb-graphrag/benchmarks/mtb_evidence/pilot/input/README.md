# `pilot/input/` — il gold non sta qui

Questa directory conteneva tre copie byte-identiche del bundle gold pilota,
tracciate dal commit `cce87f1`, mentre
`benchmarks/mtb_evidence/external_inputs/gold_bundle_manifest.json` dichiarava
`tracked_in_repository: false`. La dichiarazione era falsa, e il materiale
clinico riservato veniva distribuito a ogni checkout.

Al loro posto c'e' `external_gold_input.json`: versione del bundle, versione di
schema, i nomi dei tre file, gli sha256 attesi, l'hash aggregato, e
`availability: external_private_input`. Il manifest basta a **verificare** un
bundle quando c'e' e a **descriverlo** quando non c'e'; non basta a ricostruirlo,
ed e' esattamente la proprieta' che serve.

## Come si indica il bundle

    python -m benchmarks.mtb_evidence.evaluation.run_gold_evaluation \
      --gold-bundle <PATH>

oppure la variabile d'ambiente `MTB_GOLD_BUNDLE`. In assenza di entrambi viene
cercata la posizione convenzionale `MTB_Evidence_gold_pilot_v1_bundle` accanto
alla radice del repository. Nessuna delle tre e' un fallback silenzioso
sull'altra: se il path esplicito manca, l'errore lo nomina.

La suite core non apre mai questo ingresso, e non salta nessun test per la sua
assenza: i test che lo aprono stanno fisicamente in `backend/tests_external/gold/`.

## Cosa questa rimozione non fa

**Non purga la storia Git.** I tre file restano recuperabili da ogni commit
precedente a questa fase e da ogni clone gia' distribuito. Il repository smette
di consegnare il materiale riservato ai *nuovi* checkout; non lo cancella dal
passato.

Purgare la storia richiede una riscrittura (`git filter-repo`) e un force-push
coordinato con chiunque abbia gia' clonato — incompatibile con il perimetro di
questa fase, che non fa merge ne' push. Se la riservatezza lo richiede e'
una decisione separata, da prendere consapevolmente e non come effetto
collaterale di una pulizia.

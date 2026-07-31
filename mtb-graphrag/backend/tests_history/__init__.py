"""Test che interrogano la **storia** del repository.

Fuori dal core runtime per costruzione. Non perche' siano meno importanti — il
perimetro di una fase e' una delle proprieta' piu' forti che questo repository
verifichi — ma perche' hanno un soggetto che non tutti gli ambienti possiedono.

Un `git archive` estratto non ha `.git`. Finche' questi test stavano nella suite
core, la' si dichiaravano saltati, e i conteggi del core divergevano fra un clone
e un archivio: quarantasei skip che non dicevano niente sul codice, solo che
mancava la storia.

Spostarli e' l'unica risposta onesta. Le alternative sono peggiori:

- un manifest che registri il risultato di `git diff START..END` verificherebbe
  soltanto se stesso, perche' nessuno potrebbe ricalcolarlo per confronto;
- una fixture git sintetica proverebbe che `PhaseScope` funziona, non che
  *questa* fase ha scritto dentro il proprio perimetro, che e' la sola cosa che
  interessa.

La suite si esegue con il proprio comando:

    python -m benchmarks.mtb_evidence.evaluation.run_repository_history_validation

ed e' **obbligatoria** dove una storia c'e'. Dove non c'e', il comando dichiara
`not_applicable` e un codice d'uscita suo: non «saltata», che direbbe che il test
non e' stato eseguito, ma «questo ambiente non ha il soggetto del test».
"""

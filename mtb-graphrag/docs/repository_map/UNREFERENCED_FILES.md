# UNREFERENCED_FILES

“Apparentemente non referenziato” significa che non è emerso un import/call
site nel repository; non esclude CLI, invocazione manuale, CI esterna o altro
checkout.

| File/gruppo | Motivo | Uso manuale possibile | Certezza | Raccomandazione |
|---|---|---|---|---|
| scratch_analyze_failures.py, scratch_escat_debug.py, scratch_escat_mismatches.py | prefisso scratch, nessun import runtime | debug locale | alta | investigate, poi archive candidate |
| phase0_regenerate.py | script root di fase | rigenerazione manuale | media | investigate |
| experiments/reproducibility/*.py | CLI e riferimenti documentali, non import app | riproduzione tesi | media | keep finché serve |
| evaluation/scripts/build_*.py | builder con main e output | build/curation autorizzato | alta | keep/reference-only |
| evaluation/scripts/revise_*.py | revisioni di campagne | manutenzione artefatti | alta | investigate |
| corpus/promotion.py, rollback.py | tooling non usato dal loader runtime | release/migrazione corpus | media | keep con accesso controllato |
| backend/evaluation/run_*.py | CLI benchmark | benchmark manuale | alta | keep/reference-only |
| manual_*, exploratory/* | fixture/output/manifest | audit e confronto | alta | keep o archive candidate secondo manifest |

Non è sicuro chiamare questi file unused: gli entrypoint CLI non devono essere
importati per essere usati. Nessun file è stato cancellato o spostato.

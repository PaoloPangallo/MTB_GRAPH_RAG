# Gap e rischi

- Disease: esistono alias e pochi archi verificati, ma senza ID ontologici uniformi.
- Biomarker: non esiste una registry locale completa per gene, HGVS, fusioni, exon deletion o partner; le trasformazioni di notazione non producono ID.
- Fusioni: manca una gerarchia verificata tra gene-level e partner-specific; `RELATED` non autorizza espansione.
- Intervention: gli alias coprono pochi farmaci; classi, combinazioni e formulazioni sono incompleti. `alectinib` e `alectinib hydrochloride` non vengono fusi.
- Diagnostic: i due record locali sono identificabili per label ma privi di ontology ID e di semantica companion diagnostic.
- IDs: gli identificatori esistenti nei contratti locali non sono uniformi e non sono sempre eleggibili per exact match.
- Gerarchie: un parent/child è una relazione terminologica direzionale. `NSCLC` non rende automaticamente applicabile una prova per lung adenocarcinoma, né il contrario.
- Applicabilità: compatibilità terminologica, supporto claim-specifico e applicabilità clinica sono livelli diversi.

Espansioni pericolose da bloccare: promuovere parent → child come equivalenza, usare un drug class per un farmaco nominato, confondere sale/moiety, collassare alterazioni dello stesso gene e attribuire una prevalenza di una fusion generica al partner specifico.

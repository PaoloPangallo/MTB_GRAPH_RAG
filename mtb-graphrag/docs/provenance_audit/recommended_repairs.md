# Recommended repairs

Queste sono proposte non applicate. Nessun file applicativo o asset dati è
stato modificato dall'audit.

## A. Riparazioni di mapping

| Proposta | Fase/file | Claim interessate | Rischio | Beneficio | Semantica preservabile |
|---|---|---:|---|---|---|
| Mappare source_ids, source_unit_ids e locators dal record documentale alla qualified claim usando solo valori esistenti | trasformazione GraphEvidenceRecord → qualified claim; builder/promotion da verificare | 131 parent-only | medio-alto | alto | sì, se il join usa parent/source_record e audit |
| Conservare graph_evidence_id e source_record_ids come campi tecnici distinti | schema/materializzazione | 148 | basso | alto | sì |
| Creare un registro source-unit canonico con ID già presenti e legame exact source ID | corpus/provenance build | 17 con source unit; 131 solo dopo evidenza upstream | medio | alto | sì, senza generare identificatori |

## B. Riparazioni di propagazione

| Proposta | Fase/file | Claim interessate | Rischio | Beneficio | Semantica preservabile |
|---|---|---:|---|---|---|
| Verificare la propagazione in materializzazione prima del serializer | materialization.py, promotion.py, v3_result.py | 131 | medio | alto | sì |
| Aggiungere una guardia per parent source IDs presenti ma locator claim vuoto | promotion validation | 131 | basso in produzione, alto per retrocompatibilità | alto | sì |
| Non aggiungere fallback adapter da parent ID a fonte | adapter API | 148 | basso | evita fonti inventate | sì |

## C. Arricchimenti documentali

| Proposta | Fase/file | Claim interessate | Rischio | Beneficio | Semantica preservabile |
|---|---|---:|---|---|---|
| Aggiungere publication title/source type solo da registro documentale verificato | source registry/documentary review | 148 | medio | leggibilità | sì, separati dalla claim |
| Aggiungere locator testuale alle 131 parent-only dopo revisione | source-unit review | 131 | alto | massimo | sì, solo con annotazione verificabile |
| Mantenere PMID/DOI/NCT/URL separati e normalizzati | provenance contract | 148 | basso | evita confusione PUBMED/PMID | sì |

## D. Record senza fonte documentale attesa

- I 147 provenance container graph_evidence_record sono record tecnici: il
  parent ID non è una pubblicazione e non va mostrato come claim verificata.
- I 12 unsupported_association/unresolved_association sono record tecnici ma
  nel repository corrente hanno source unit e locator; non sono claim positive.
- Le 4 claim deprecate sono technical records nella response e hanno locator;
  non devono essere reintrodotte come claim attive.

## E. Ispezione manuale necessaria

1. I 131 parent-only: verificare se il source unit esiste upstream e se il
   locator può essere propagato senza cambiare il significato della claim.
2. CLM-6016e0878e055658200e, il solo active claim con parent DOI-only:
   confermare il DOI senza convertirlo in PMID.
3. CLM-5ce532268b4aa1661311, che ha source-unit ID e locator ma un source-unit
   ID non ritrovato negli artefatti ausiliari di review.
4. Le 45 claim direction resistance in stato parent-only; quattro resistance
   hanno già un locator diretto e vanno usate come controllo di mapping.
5. Le 2 claim preclinical e le 3 aggregate prima di qualunque arricchimento.

Ogni intervento futuro dovrebbe produrre prima un diff di mapping e un audit
di non-invenzione; non è autorizzato da questo commit.

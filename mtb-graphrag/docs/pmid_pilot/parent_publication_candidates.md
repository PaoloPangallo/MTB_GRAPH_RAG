# Parent publication candidates

Questi record servono a valutare la recuperabilità di un passaggio, non a
promuovere la provenance della claim.

| claim_id | parent IDs locali | candidato esaminato | esito |
|---|---|---|---|
| CLM-1d3ba8b6ae49232969c7 | 30420614 | PMID 30420614, *Derazantinib ... FGFR2 gene fusion-positive intrahepatic cholangiocarcinoma* | candidato direttamente compatibile; `DIRECT_SUPPORT` testuale, `parent_candidate` documentale |
| CLM-0269a5c7db107cd8a893 | 24893891 | PMID 24893891, *AZD9291 ... T790M-mediated resistance* | candidato parziale; codice AZD9291 non collegato a `osimertinib` nel record claim |
| CLM-0f234bc9c53847910521 | 24736079; 27130468; 27432227; 29373100; 29376144; 29650534 | PMID 24736079, *ALK G1202R ... resistance to alectinib* | passaggio forte ma parent multi-pubblicazione; `AMBIGUOUS` |
| CLM-1e4f404ac84ee591fbda | 29182496 | PMID 29182496, *Phase II Study of BGJ398 ... FGFR-Altered Advanced Cholangiocarcinoma* | candidato parziale; BGJ398 e scope ampio |

Regola applicata: il PMID viene mantenuto in `PARENT_LEVEL`, il
`source_unit_id` resta `UNAVAILABLE`, il locator è `ABSTRACT` solo come
posizione del testo candidato e `publication_link_status` resta
`parent_candidate`. Nessun valore è stato copiato nella claim repository.

# Pilot claim selection

## Gruppo A — CLAIM_VERIFIED_LOCATOR

Sono stati scelti 12 dei 17 casi diretti. La copertura intenzionale è:

| claim_id | profilo | PMID | motivo |
|---|---|---:|---|
| CLM-091cf6602db85e2a2d41 | FGFR2/TACC3, therapeutic sensitivity, clinical | 24550739 | include un esito di stable disease su ponatinib |
| CLM-0e59264facd7b2df0e67 | EML4-ALK/I1171S, resistance, clinical | 25393796 | relazione acquisita alectinib-resistance |
| CLM-5ce532268b4aa1661311 | EML4-ALK/C1156Y, resistance, clinical | 26698910 | progressione/resistenza a crizotinib |
| CLM-4ffe85304f3ef5533b58 | EGFR L858R, aggregate sensitivity, clinical | 24457318 | coorte EGFR-TKI e predittori di risposta |
| CLM-90e863f00f134fc3cd3d | FGFR2/BICC1, aggregate sensitivity, preclinical | 24122810 | NIH3T3 e soppressione della trasformazione |
| CLM-8941c177da91f66ff93a | FGFR2/BICC1, diagnostic | 24122810 | definizione di sottotipo molecolare |
| CLM-1fc4af943701d57d45ad | EGFR L858R, gefitinib sensitivity | 24736073 | gruppo gefitinib in NSCLC EGFR-mutato |
| CLM-89ea67ee7946d9ccd552 | EGFR L858R, erlotinib sensitivity | 24736073 | gruppo erlotinib nello stesso abstract |
| CLM-5ce49705979f72f174e9 | EGFR, regimen sensitivity, clinical | 37879444 | braccio amivantamab-carboplatino-pemetrexed |
| CLM-4a89bb28592af7ebaccf | EGFR, regimen sensitivity, clinical | 38942080 | amivantamab-lazertinib contro osimertinib |
| CLM-a7e1c40b794d2c4d4ca8 | FGFR2/AHCYL1, diagnostic | 24122810 | secondo partner di fusione diagnostico |
| CLM-5071bb2d8657ac0fbed0 | FGFR2/AHCYL1, aggregate sensitivity, preclinical | 24122810 | confronto con l'aggregate BICC1 |

I claim A riportano PMID, source unit e locator nel record della claim. Il
  testo locale ha però precisione `ABSTRACT`, salvo i locator full-text già
  esistenti nel repository; per questa selezione i passaggi usati sono tutti
  abstract locali.

## Gruppo B — PARENT_PUBLICATION_AVAILABLE

| claim_id | parent PMID/candidato | claim | motivo |
|---|---:|---|---|
| CLM-1d3ba8b6ae49232969c7 | 30420614 | FGFR2 fusion / derazantinib / iCCA / sensitivity | candidato molto pertinente, ma nessun source unit nella claim |
| CLM-0269a5c7db107cd8a893 | 24893891 | EGFR T790M / osimertinib / sensitivity | testo reale, ma codice AZD9291 e biomarcatore/setting da delimitare |
| CLM-0f234bc9c53847910521 | 24736079 tra 6 PMID parent | ALK G1202R / alectinib / resistance | un candidato contiene la relazione completa; il parent è multi-pubblicazione |
| CLM-1e4f404ac84ee591fbda | 29182496 | FGFR2 fusion / infigratinib / sensitivity | candidato clinico, ma l'abstract usa il codice BGJ398 e malattia ampia |

Per il Gruppo B il campo `identifier_scope` è sempre `PARENT_LEVEL` e il
`publication_link_status` è `parent_candidate`.

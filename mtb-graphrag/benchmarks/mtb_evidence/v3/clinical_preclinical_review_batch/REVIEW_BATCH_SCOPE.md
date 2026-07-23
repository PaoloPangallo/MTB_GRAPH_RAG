# Perimetro della revisione clinico/preclinica

- **Hash del perimetro:** `dc98d5468d589138ddf243eabacd99164d83a9db256112d5691bc4ade6fdb90f`
- **Fonti nel batch:** 3

## Perche' queste tre

L'audit strutturale ha letto i segnali delle nove fonti residue e ne ha
classificate tre `clinical_preclinical_split_required`: contengono sia una
componente clinica sia una preclinica, e un profilo unico le fonderebbe.

L'audit si e' fermato li'. Un segnale dice **che** le due componenti esistono,
non **quali** statement appartengano all'una e quali all'altra: tutti e sette
gli statement di queste fonti sono rimasti `candidate_ambiguous`. Questa fase
legge le fonti primarie per scioglierlo.

## Fonti

| Unita' | PMID | Statement | Full text | Segnali | Rischio |
| --- | --- | ---: | --- | ---: | --- |
| `PU-PMID-22235099-cohort-1` | 22235099 | 3 | `PMC3311875` | 185 | low (3) |
| `PU-PMID-23344087-cohort-1` | 23344087 | 2 | **assente** | 11 | low (2) |
| `PU-PMID-31358542-cohort-1` | 31358542 | 2 | `PMC6858956` | 110 | medium (8) |

## Disponibilita' documentale

- Con full text pubblico: **2** su 3
- Solo abstract: **1**

Per `PU-PMID-23344087-cohort-1` il full text non e' in PMC. La verifica documentale si ferma
a cio' che l'abstract espone, e la decisione strutturale deve dirlo invece
di concludere lo split su una base che non lo sostiene.

## Che cosa questa fase non fa

Non produce revisioni umane. Il tetto assegnabile e'
`source_checked_review_proposal`, con `human_reviewed = false` e
`requires_author_approval = true`: le proposte vanno approvate dall'autore
prima di poter diventare gold, e restano non propagabili fino ad allora.


# Perimetro dell'audit strutturale

- **Hash del perimetro:** `3dbf38590ea0bb2449adacee383fe10f9ba6152178bfc5417ddf5f6c7afb8cba`
- **Unita' residue:** 9

## Perche' sono nove e non otto

La specifica prevedeva otto unita' residue, assumendo che PMID 22277784 fosse
fra le `cohort_partially_resolved` e andasse sottratta. Non lo era: quella
fonte era classificata **`insufficient_source_information`**, cioe' nel bucket
piu' debole, pur avendo dieci statement.

La differenza di conteggio e' il dettaglio meno interessante. Il fatto e' che
la fonte di cui oggi sappiamo con certezza che contiene una coorte clinica e
tre pannelli su cellule non era stata segnalata **affatto** — non e' stata
mancata per poco. Il segnale che avrebbe dovuto accenderla vive nel full text,
e il rilevatore leggeva solo l'abstract e la distribuzione degli statement.

Il perimetro segue quindi il criterio della specifica — le unita'
`cohort_partially_resolved` meno quella gia' revisionata — e il controllo
confronta l'insieme derivato con quello dichiarato invece di fidarsi di un
numero.

## Unita' nel perimetro

| Unita' | Statement | Interventi | Rischio |
| --- | ---: | --- | --- |
| `PU-PMID-22235099-cohort-1` | 3 | crizotinib | low (3) |
| `PU-PMID-22285168-cohort-1` | 2 | erlotinib | medium (8) |
| `PU-PMID-23344087-cohort-1` | 2 | crizotinib | low (2) |
| `PU-PMID-27130468-cohort-1` | 1 | alectinib hydrochloride | medium (4) |
| `PU-PMID-27870574-cohort-1` | 2 | infigratinib | low (2) |
| `PU-PMID-27959700-cohort-1` | 3 | osimertinib | low (3) |
| `PU-PMID-28958502-cohort-1` | 2 | dacomitinib | low (2) |
| `PU-PMID-31358542-cohort-1` | 2 | brigatinib, ceritinib | medium (8) |
| `PU-PMID-32203698-cohort-1` | 1 | pemigatinib | medium (4) |

## Disponibilita' delle fonti

- Con abstract: 9
- Con full text pubblico: 0


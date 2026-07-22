# Ablation di reporting

- **Modello del braccio libero:** non eseguito

I quattro bracci ricevono gli stessi record congelati, nello stesso ordine. Il retrieval non viene rieseguito: qualunque differenza qui sotto e' attribuibile al modo di scrivere il report, non a cio' che e' stato trovato.

| Metrica | raw_records | structured_report_unverified | structured_report_verified |
| --- | --- | --- | --- |
| citation_accuracy | 1.000 | 1.000 | 1.000 |
| qualifier_preservation | 0.278 | 0.000 | 1.000 |
| context_omission_rate | 0.722 | 1.000 | 0.000 |
| unsupported_claim_rate | 0.000 | 0.000 | 0.000 |
| structural_coverage | 1.000 | 1.000 | 1.000 |
| abstention_accuracy | 1.000 | 1.000 | 1.000 |

## Come leggere questi numeri

`raw_records` e' il limite superiore di conservazione per cio' che il grafo contiene: nessuna sintesi, quindi nulla puo' andare perso nella scrittura.

**Il vantaggio del braccio verificato sui qualificatori non e' merito della scrittura.** I qualificatori — setting, linea di terapia, popolazione — non esistono nel grafo: vivono solo nei profili clinici annotati a mano. Il braccio verificato e' l'unico che li consulta, quindi e' l'unico che puo' riportarli. Gli altri bracci non li omettono per negligenza: non li hanno.

La lettura corretta e' quindi: *la verifica delle fonti aggiunge informazione che il retrieval non puo' fornire*, non *il report verificato scrive meglio*. E' un argomento a favore dei profili annotati, non della resa testuale.

Quattro casi: i valori descrivono questo campione e non stimano una popolazione.

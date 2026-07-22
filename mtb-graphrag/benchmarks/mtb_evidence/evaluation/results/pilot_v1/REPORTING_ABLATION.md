# Ablation di reporting

- **Modello del braccio libero:** gpt-oss:120b-cloud

I quattro bracci ricevono gli stessi record congelati, nello stesso ordine. Il retrieval non viene rieseguito: qualunque differenza qui sotto e' attribuibile al modo di scrivere il report, non a cio' che e' stato trovato.

| Metrica | free_llm_summary | raw_records | structured_report_unverified | structured_report_verified |
| --- | --- | --- | --- | --- |
| citation_accuracy | 0.972 | 1.000 | 1.000 | 1.000 |
| qualifier_preservation | 0.271 | 0.278 | 0.000 | 1.000 |
| context_omission_rate | 0.729 | 0.722 | 1.000 | 0.000 |
| unsupported_claim_rate | 0.036 | 0.000 | 0.000 | 0.000 |
| structural_coverage | 0.325 | 1.000 | 1.000 | 1.000 |
| abstention_accuracy | 1.000 | 1.000 | 1.000 | 1.000 |

## Come leggere questi numeri

`raw_records` e' il limite superiore di conservazione per cio' che il grafo contiene: nessuna sintesi, quindi nulla puo' andare perso nella scrittura.

**Il vantaggio del braccio verificato sui qualificatori non e' merito della scrittura.** I qualificatori — setting, linea di terapia, popolazione — non esistono nel grafo: vivono solo nei profili clinici annotati a mano. Il braccio verificato e' l'unico che li consulta, quindi e' l'unico che puo' riportarli. Gli altri bracci non li omettono per negligenza: non li hanno.

La lettura corretta e' quindi: *la verifica delle fonti aggiunge informazione che il retrieval non puo' fornire*, non *il report verificato scrive meglio*. E' un argomento a favore dei profili annotati, non della resa testuale.

### Dove la sintesi libera perde davvero

Qui il confronto e' pulito, perche' entrambi i bracci ricevono gli stessi record e nessuno dei due consulta i profili annotati:

- **Copertura strutturale 0.325** contro 1.000 dei bracci deterministici. La sintesi libera menziona una frazione di cio' che il retrieval ha trovato: il resto sparisce senza che il testo segnali l'omissione.
- **Claim non ancorate 0.036** contro 0.000. Una parte delle affermazioni non trova riscontro nei record ricevuti, e su un report di evidenza e' il difetto che conta di piu': un lettore non puo' distinguerle dalle altre.

Queste due differenze **sono** attribuibili al modo di scrivere, perche' l'input era identico. E' il risultato che sostiene la tesi sul reporting strutturato — non il vantaggio sui qualificatori, che viene dai profili.

Quattro casi: i valori descrivono questo campione e non stimano una popolazione.

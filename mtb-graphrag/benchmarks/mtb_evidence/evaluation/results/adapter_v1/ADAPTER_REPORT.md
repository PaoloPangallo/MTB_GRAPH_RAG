# Adapter V2 → EvidenceStatement — fedelta' della conversione

- **Snapshot:** `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`
- **Record compatibili:** 199
- **Convertiti:** 147
- **Esito:** ACCETTATO

Un record e' *compatibile* se e' un'evidenza con almeno una citazione. I record
di trial descrivono uno studio, non una proposizione clinica, e diventeranno
riferimenti di altri statement: contarli fra i fallimenti misurerebbe la cosa
sbagliata.

## Misure

| Misura | Valore | Numeratore | Denominatore |
| --- | ---: | ---: | ---: |
| `conversion_success_rate` | 1.0000 | 147 | 147 |
| `source_field_preservation` | 1.0000 | 1034 | 1034 |
| `provenance_preservation` | 1.0000 | 147 | 147 |
| `unknown_field_honesty` | 1.0000 | 1114 | 1114 |

`source_field_preservation` ha come denominatore **solo i campi effettivamente
presenti** nel record originale: chiedere di piu' misurerebbe la completezza del
grafo, non la fedelta' dell'adapter.

`unknown_field_honesty` verifica il contrario di tutte le altre: che un dato
assente sia rimasto assente. Un adapter che riempisse i vuoti con valori
plausibili otterrebbe punteggi migliori altrove e falsificherebbe la baseline.

## Presenza delle fonti nello snapshot

| Stato | Riferimenti |
| --- | ---: |
| `citation_only` | 134 |
| `node` | 5 |
| `unknown` | 22 |

`citation_only` significa che il PMID esiste dentro `Evidence.citation_id` ma non
come nodo `Publication`. E' recuperabile come citazione e non ha metadati
bibliografici: appiattirlo su `node` nasconderebbe un limite reale del grafo.

## Che cosa il grafo non contiene

I qualificatori clinici — setting, stadio, linea di terapia, resezione,
popolazione — non sono rappresentati dallo schema del grafo V2. L'adapter li
lascia vuoti e lo registra: non e' un difetto della conversione ma la misura del
punto di partenza, ed e' esattamente cio' che la V3 esiste per colmare.

Anche il disegno dello studio (`evidence_type` nel senso V3) e' assente. Il campo
`evidence_type` del grafo contiene i valori CIViC — Predictive, Prognostic — che
descrivono il *tipo di affermazione* e nel modello V3 corrispondono a
`evidence_scope`. Mapparlo su `evidence_type` sarebbe un errore di categoria.

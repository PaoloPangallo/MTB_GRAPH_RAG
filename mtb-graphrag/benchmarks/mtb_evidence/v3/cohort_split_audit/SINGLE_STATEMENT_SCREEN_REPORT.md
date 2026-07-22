# Screening del rischio di split non rilevato

- **Fonti esaminate:** 102 su 102
- **Fonti a statement singolo:** 73
- **Candidati allo split:** 43
- di cui a statement singolo: 32
- **Tasso di rischio residuo:** 42.2%

## Perche' lo screening copre tutte le fonti

La specifica lo chiedeva sulle fonti a statement singolo, che erano il rischio
sospettato. Il caso PMID 22277784 ha mostrato che il rischio non e' legato al
numero di statement: quella fonte ne aveva dieci ed era invisibile al rilevatore
in produzione. Limitare lo screening alle single-statement avrebbe riprodotto
l'assunzione appena smentita, quindi copre tutte e 102.

## Distribuzione dei verdetti

| Verdetto | Fonti |
| --- | ---: |
| `split_not_indicated` | 47 |
| `split_possible` | 0 |
| `split_likely` | 19 |
| `split_required` | 30 |
| `insufficient_information` | 6 |

`insufficient_information` non e' un verdetto tranquillo. E' il bucket in cui
PMID 22277784 era finito, e la priorita' di revisione per quelle fonti resta
media, non bassa.

Anche `split_not_indicated` va letto con cautela: 47 verdetti negativi sono
stati formulati sul **solo abstract**, e sono quindi negativi deboli. Il campo
`negative_verdict_is_weak` li marca uno per uno. Per trasformarli in negativi
forti servirebbe il full text, che per queste fonti non e' stato recuperato.

## Primi candidati

| Fonte | Statement | Verdetto | Segnali | Priorita' |
| --- | ---: | --- | --- | --- |
| `PMID:32973082` | 1 | `split_required` | clinical, in_vitro, in_vivo | high |
| `PMID:23658459` | 1 | `split_required` | clinical, comparator, in_vitro, in_vivo | high |
| `PMID:21791641` | 1 | `split_required` | clinical, in_vitro | high |
| `PMID:24550739` | 2 | `split_required` | clinical, in_vitro | high |
| `PMID:24675041` | 3 | `split_required` | clinical, in_vitro, in_vivo | high |
| `PMID:31585938` | 1 | `split_required` | clinical, in_vitro, in_vivo | high |
| `PMID:25228534` | 4 | `split_required` | clinical, in_vitro | high |
| `PMID:24893891` | 3 | `split_required` | clinical, in_vitro, in_vivo | high |
| `PMID:39269178` | 1 | `split_required` | clinical, in_vitro, in_vivo | high |
| `PMID:27179038` | 1 | `split_required` | clinical, in_vitro, in_vivo | high |
| `PMID:27432227` | 3 | `split_required` | clinical, in_vitro | high |
| `PMID:18408761` | 4 | `split_required` | clinical, in_vitro, in_vivo | high |
| `PMID:19147750` | 1 | `split_required` | clinical, in_vitro | high |
| `PMID:15118125` | 1 | `split_required` | clinical, in_vitro | high |
| `PMID:17177598` | 1 | `split_required` | clinical, in_vitro | high |

## Che cosa questo screening non e'

Non e' una curation. Nessuna unita' e' stata modificata, nessun profilo
generato, nessuna revisione prodotta. Un candidato e' una fonte **da guardare**,
non una fonte sbagliata: i segnali dicono che la struttura potrebbe essere
multipla, e solo la lettura puo' dirlo.


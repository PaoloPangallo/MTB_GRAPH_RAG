# Audit dei tre record non terapeutici

Perimetro: i tre graph evidence ID che la migrazione shadow ha lasciato senza
claim. Il criterio di selezione è verificabile e chiude il perimetro: sono gli
unici tre dei 147 record con direzione non terapeutica (`diagnostic` o
`prognostic`) e nessun intervento né nello statement né nelle righe V2.

Materiali usati: corpus operativo, source profile unit, lineage V2, cache degli
abstract. Solo abstract, nessun full text. Il gold non è stato letto.

---

## `evidence:347` — prognostico dichiarato, predittivo nella fonte

| Campo | Valore |
|---|---|
| Statement legacy | `ES-V2-evidence-347` |
| Fonte | `PMID:24662454` — FLEX study, analisi secondaria |
| Disease | Lung Non-small Cell Carcinoma |
| Biomarcatore | EGFR L858R |
| Direction / scope (grafo) | `prognostic` / `prognostic` |
| Evidence type / level | `unknown` / B (civic) |
| Polarity | `supports` |
| Interventi nello statement | nessuno |
| Interventi nelle righe V2 | nessuno |
| Traversal | `evidence_containing_l858r` |
| Source unit | `PU-PMID-24662454-cohort-1`, `awaiting_source_review`, `is_evaluable: false`, 0 source span |
| Locator | nessuno nel corpus; l'abstract è disponibile |
| Review status | `pending_verification` |

**Verdetto: `non_therapeutic_claim_unresolved`.**

La fonte è un'analisi secondaria dello studio di fase III FLEX che misura *se
l'effetto di cetuximab sia modulato dallo stato mutazionale di EGFR*. È un
disegno predittivo, non prognostico. In tutto l'abstract L858R compare una volta
sola, e non in un risultato: «The most common mutations were exon 19 deletions
and L858R (124 of 133 patients; 93%)» — una frase che descrive la composizione
mutazionale della popolazione screenata. La conclusione riguarda cetuximab: «The
survival benefit ... is not limited by EGFR mutation status.»

Quindi la direzione `prognostic` del grafo **è contraddetta dalla fonte**:
nessun esito è associato a L858R indipendentemente dal trattamento. Seguire la
stringa avrebbe prodotto un claim prognostico che il documento non sostiene, ed è
il motivo per cui il contratto vieta di dedurre il ruolo dalla sola etichetta.

Il record non può nemmeno essere ritipizzato come predittivo: non porta alcun
intervento, e attribuirgli cetuximab sarebbe inventare esattamente ciò che questa
linea di lavoro esiste per non inventare.

Resta sospeso e non concluso: con il solo abstract non si può escludere che il
full text contenga un'analisi prognostica di sottogruppo. Serve il full text.

---

## `evidence:1846` e `evidence:1847` — diagnostici, e sostenuti

| Campo | `evidence:1846` | `evidence:1847` |
|---|---|---|
| Statement legacy | `ES-V2-evidence-1846` | `ES-V2-evidence-1847` |
| Fonte | `PMID:24122810` | `PMID:24122810` |
| Disease | Cholangiocarcinoma | Cholangiocarcinoma |
| Biomarcatore | FGFR2::BICC1 Fusion | FGFR2::AHCYL1 Fusion |
| Direction / scope (grafo) | `diagnostic` / `unknown` | `diagnostic` / `unknown` |
| Evidence type / level | `unknown` / B (civic) | `unknown` / B (civic) |
| Polarity | `supports` | `supports` |
| Interventi (statement e V2) | nessuno | nessuno |
| Traversal | `evidence_fusion_profiles_only` | `evidence_fusion_profiles_only` |
| Source unit | `PU-PMID-24122810-cohort-1`, `awaiting_first_review` | idem |
| Locator | abstract, 4 frasi citate | abstract, 4 frasi citate |
| Review status | `pending_verification` | `pending_verification` |

**Verdetto per entrambi: `diagnostic_claim_supported`.**

L'abstract identifica esplicitamente le due fusioni per nome, riporta che le
fusioni FGFR2 si trovano nel colangiocarcinoma quasi esclusivamente nel sottotipo
intraepatico (9/66, 13,6%), che sono rare o assenti negli altri tumori esaminati
(colorettale 1/149, epatocellulare 1/96, gastrico 0/212), e che sono mutuamente
esclusive con KRAS/BRAF. Titolo e conclusione dicono che queste fusioni
definiscono un sottotipo molecolare e giustificano una nuova classificazione.

È un claim diagnostico nel senso classificatorio, e il documento lo sostiene.

Due limiti sono registrati con il claim e non vanno persi:

**La prevalenza non è separabile per partner di fusione.** Il 13,6% è riportato
per «the FGFR2 fusion» nel suo insieme. Ripartirlo fra BICC1 e AHCYL1
attribuirebbe a ciascuno un numero che la fonte fornisce solo congiuntamente — lo
stesso errore che l'adjudication ha rifiutato sugli aggregati terapeutici, qui
sul versante diagnostico. Il claim afferma l'appartenenza al sottotipo, non una
frequenza propria.

**L'utilità clinica non è affermata.** La fonte propone una nuova classificazione
molecolare; non dice che esista un test diagnostico validato o approvato.
`clinical_validation_asserted` resta falso.

Nessuno dei due è un claim prognostico: l'abstract non riporta alcun esito.

---

## Esito

| Verdetto | Record |
|---|---|
| `diagnostic_claim_supported` | `evidence:1846`, `evidence:1847` |
| `non_therapeutic_claim_unresolved` | `evidence:347` |

Claim diagnostici approvati: 2. Claim prognostici approvati: 0. Interventi
inventati: 0. Parent che restano senza claim: `evidence:347` — più
`evidence:3811` ed `evidence:4759`, già senza claim dall'adjudication.

I due claim diagnostici sono **simulati, non materializzati**: il repository
shadow non è stato rigenerato e il loro `review_status` è
`audited_not_materialised`. Entrambe le source unit richiedono ancora revisione
umana della fonte primaria.

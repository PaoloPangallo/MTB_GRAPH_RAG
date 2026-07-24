# Differenze di rappresentazione V2/V3

## Unità V2

Il record V2 congelato è una riga restituita da un traversal. Per i traversal
evidence-farmaco, la riga rappresenta la combinazione tra un nodo Evidence e un
farmaco collegato. Lo stesso `evidence_id` può quindi apparire più volte.
L'ordine serializzato è l'ordine storico, non uno score disponibile.

I traversal non hanno un solo contratto:

- alcuni partono dal gene o dal molecular profile;
- alcuni selezionano l'alterazione nel nome del profile;
- altri partono da farmaci o PMID attesi;
- non tutti applicano disease, biomarcatore e intervento come vincoli
  congiuntivi.

Per questo la baseline V2 è una unione di percorsi di audit e non equivale al
risultato di un unico predicato strutturale.

## EvidenceStatement

L'EvidenceStatement è una proposizione materializzata dal record del grafo.
Nel corpus corrente i 147 graph evidence ID corrispondono a 147 statement:
la cardinalità osservata è uno-a-uno. Questa cardinalità non preserva però le
righe multi-farmaco: 11 righe V2 secondarie confluiscono nello statement che
mantiene un solo intervento.

Di conseguenza un record V2 può:

- diventare uno statement;
- condividere lo statement con altre righe V2 dello stesso graph evidence ID;
- non diventare uno statement se non è una Evidence materializzabile, anche se
  nel pilot corrente questo caso non si verifica;
- diventare più statement in una futura versione dell'adapter, ma non nel
  corpus 2.0 congelato.

## Source profile unit e qualification link

La source profile unit descrive una porzione contestuale della fonte: coorte,
modello, pannello o sottogruppo. Non è un duplicato dello statement. Un
qualification link collega statement e unità e porta status, directness e
decisioni di prima revisione.

Nel corpus:

- 109 unità sono attive;
- 108 unità attive sono raggiunte dai link;
- 201 link collegano gli statement;
- 128 statement hanno un link;
- 18 statement hanno da 2 a 7 link;
- uno statement non ha link.

Un EvidenceStatement può quindi avere zero, una o più source profile unit. Le
unità multiple non aumentano il candidate count: arricchiscono provenance,
warning e soft scoring.

## QualifiedEvidenceView

La QualifiedEvidenceView è il join read-only per statement. Esistono 147 view,
una per EvidenceStatement. La view non materializza una riga per profile unit e
non ripristina le righe V2 multi-farmaco.

## Tipi di divergenza

| Evento | Significato |
|---|---|
| Perdita reale di evidence ID | statement assente o mapping graph-ID fallito; non osservata nel pilot |
| Filtro nativo | statement presente, ma il contratto V3 rifiuta disease/biomarker/etc. |
| Deduplicazione | più righe V2 dello stesso graph ID diventano uno statement |
| Conversion loss | un campo di una riga duplicata, qui l'intervento, non è rappresentato |
| Espansione strutturale | uno statement ha più profile unit senza diventare più candidati |
| Overreach | il matcher accetta il gene pur non accettando l'alterazione richiesta |

La parità di conteggio tra righe V2 e statement V3 non è quindi un obiettivo
corretto. La coverage va dichiarata separatamente per record, graph evidence ID,
statement, fonte, terapia e proposizione.

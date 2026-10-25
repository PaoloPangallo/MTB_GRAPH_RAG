# Limiti del pilot v2.0

Campione di 7 chiamate: sufficiente per dimostrare che il transport
funziona in modo affidabile e che almeno un enrichment grounded è
raggiungibile, non sufficiente per stimare un tasso di successo stabile
(2/3 decision QUOTE accettate su questo campione, intervallo troppo
piccolo per generalizzare).

Il rigetto del Caso 2 (primo paper) mostra che anche con lo schema
semplificato il modello può dichiarare un `source_unit_id` e produrre una
quote che non è letteralmente in quella specifica SourceUnit — il
controllo di fedeltà testuale resta indispensabile, lo schema più
semplice riduce gli errori di conformità ma non elimina gli errori di
citazione.

Le 2 astensioni con campi incoerenti (`source_unit_id` popolato nonostante
`decision=ABSTAIN`) indicano che anche il contratto minimale non elimina
del tutto l'incoerenza — solo la sposta da un rigetto totale di trasporto
(v1.1) a un'anomalia registrabile e non promuovibile a livello semantico,
che è l'esito voluto ma resta un limite del modello da monitorare su
campioni più ampi.

Il controllo "quote non presa da CaseContext o candidate" e "drug presente
nel passaggio" sono euristiche lessicali (sottostringa/overlap), non
semantiche complete — non esercitate a fondo in questo campione (nessun
rigetto di questo tipo osservato).

Nessun confronto diretto con dati reali di pazienti; cache documenti
riusata invariata, nessun nuovo documento recuperato.

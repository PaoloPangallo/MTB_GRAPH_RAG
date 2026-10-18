# Valutazione semantica della narrazione del dossier

La valutazione confronta le risposte già salvate con il dossier ricevuto. Le
risposte originali e il loro esito deterministico rimangono conservati. Il
giudizio riguarda la fedeltà della presentazione, distinta dalla verifica
scientifica delle pubblicazioni e dall'applicabilità clinica.

## Materiale e criteri fissati prima delle chiamate al valutatore

- Dieci risposte del narratore: sei fixture sintetiche e quattro sottoinsiemi
  archiviati. Questi ultimi riutilizzano tre pubblicazioni BRAF: il caso che le
  raccoglie non costituisce tre nuove osservazioni indipendenti.
- Dieci controlli del valutatore: otto errori intenzionali e due parafrasi fedeli.
  Gli errori cambiano esito, popolazione, combinazione, composizione molecolare,
  significato di un controllo, raccomandazione, negazione o confronto tra studi.
- Dimensioni: attribuzione, esiti, composizione molecolare, popolazione,
  intervento, incertezza, significato dei controlli, collegamento al caso,
  copertura dei contenuti importanti e confronto tra studi.

Il valutatore riceve esclusivamente il contenuto da confrontare. I verdetti
attesi dei controlli e le osservazioni della revisione Codex restano fuori dal
suo ingresso. Ogni rilievo deve indicare un estratto letterale della narrazione
e un estratto del dossier, collegati con JSON Pointer verificati localmente.
Questa verifica rende rintracciabile il rilievo; la sua correttezza resta oggetto
di valutazione.

Un errore critico o sostanziale richiede revisione. Un rilievo minore produce
un'accettazione con note. Una spiegazione senza rilievi è accettabile nel
perimetro del materiale fornito. Un problema tecnico o riferimenti di prova
invalidi rendono inutilizzabile il giudizio, senza convertirlo in accettazione.

La prova di sensibilità richiede il riconoscimento degli otto errori
intenzionali. I due controlli fedeli verificano i falsi allarmi. Si riportano
separatamente trasporto, verificabilità degli estratti e verdetto semantico.
Una buona riuscita su questi pochi casi non dimostra affidabilità generale.

## Due letture con ruoli dichiarati

La revisione Codex confronta direttamente i dati salvati. Una seconda lettura
utilizza il provider configurato con un prompt da valutatore. Se il modello è
lo stesso del narratore, il report lo indica: le due chiamate hanno ruoli
distinti, ma non costituiscono una validazione indipendente tra modelli.
La revisione Codex è a sua volta una valutazione assistita da modello, non un
giudizio umano né un gold standard clinico.

La sintesi finale conserva eventuali disaccordi. I rilievi distinguono omissioni
della spiegazione da informazioni disponibili nelle schede e distinguono i
limiti già presenti nel dossier dagli errori introdotti dalla narrazione.

## Revisione del valutatore dopo il primo tentativo

Il secondo tentativo vincola i riferimenti alle prove a un elenco di campi
effettivi e rende esplicito il criterio sulle raccomandazioni terapeutiche,
mancato nella prima calibrazione. Il controllo sintetico sul falso accordo
fra studi è stato corretto per mantenere coerenti identità dello studio e
identità del documento. Il primo tentativo resta archiviato integralmente.
La seconda calibrazione riutilizza controlli già esaminati: la generalizzazione
richiede un insieme di prove separato. Le dieci spiegazioni valutate restano
quelle originali.

## Riproduzione

```powershell
python evaluation/run_narrator_semantic_audit.py --out evaluation/narrator_semantic_audit_prepared
python evaluation/run_narrator_semantic_audit.py --live --out evaluation/narrator_semantic_audit_new_trial
python -m evaluation.build_narrator_semantic_report
```

Il primo comando prepara gli ingressi senza chiamare il modello. Il secondo
invia i dati al provider e conserva risposte, prompt, impronte e rilievi in una
cartella nuova. Il terzo ricostruisce il rapporto sullo snapshot finale v11 già
archiviato e sulla revisione Codex; una nuova prova va confrontata separatamente.
Questa
valutazione resta un audit: il verificatore deterministico della produzione
mantiene il proprio ruolo e il proprio esito.

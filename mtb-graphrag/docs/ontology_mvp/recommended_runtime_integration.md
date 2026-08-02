# Raccomandazione per il runtime

Raccomandazione: **B. USARE SOLO PER NORMALIZZAZIONE**, in una futura fase separata e dopo aver ampliato gli asset con identificatori canonici verificati.

La prima integrazione ammissibile dovrebbe limitarsi a equivalenze esatte e alias locali con provenienza. Non dovrebbe usare `DESCENDANT`, `ANCESTOR`, `RELATED` o `CLASS_MATCH` per ammettere claim, cambiare gate, score, bucket o ranking.

Una fase successiva potrebbe esporre il match come spiegazione UI o come traccia per revisione manuale. L’espansione della query e un gate secondario richiederebbero benchmark dedicati, casi positivi/negativi e validazione indipendente; non sono implementati qui.

Possibili usi futuri, non implementati:

- normalizzare `CaseContext` e claim mantenendo il valore originale;
- fornire ai gate un segnale diagnostico separato;
- mostrare il motivo del match e il livello di generalizzazione;
- aiutare un agente IA solo con concetto, path e provenance locali;
- tracciare ogni espansione parent/child senza trasformarla in applicabilità clinica.

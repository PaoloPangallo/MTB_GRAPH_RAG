# 12 — Limitazioni

## 1. Il lexicon è una lista chiusa

`narrative-lexicon/1.0` contiene 24 pattern per il linguaggio prescrittivo, 22
per le affermazioni di supporto, e i marcatori di negazione, incertezza e
assenza documentale. Copre **le formulazioni elencate**, non l'italiano o
l'inglese in generale.

Una parafrasi nuova può non essere riconosciuta. È la stessa limitazione, e la
stessa scelta, del rilevatore di istruzioni di controllo (ISS-010): un elenco
esplicito è ispezionabile e discutibile; un classificatore addestrato non lo
sarebbe, e richiederebbe di fidarsi di un secondo modello.

La correzione emersa dal benchmark — la variante «segnale documentale» — è la
dimostrazione concreta del limite: il lexicon andrà esteso man mano che si
osservano formulazioni nuove.

## 2. Il verifier controlla la fedeltà, non la correttezza clinica

Verifica che la narrativa non contraddica il dossier. Non verifica che il
dossier abbia ragione. Una narrativa fedele a un dossier sbagliato passa — ed è
corretto che passi: il dossier è la sorgente di verità, e i suoi limiti sono
documentati altrove.

## 3. Il campione manuale non è annotato

`evaluation/gold/narrative_manual_review.csv` ha 25 righe e sette colonne del
revisore **vuote**. Finché restano vuote, la fedeltà narrativa è dimostrata
rispetto al verifier automatico, non a un giudizio esperto.

È lo stesso limite di ISS-011 per il campione GCA v3, e va dichiarato con la
stessa franchezza.

## 4. Il benchmark è in larga parte sintetico

20 dossier su 25 sono costruiti dal codice del benchmark, conformi al contratto
reale ma non prodotti da run reali. La ragione è misurata: il campione REPLAY
disponibile non produce alcuna candidate `DIRECT`. Con 16 candidate raggiungibili
end-to-end e 5 casi sintetici, un benchmark interamente reale non era possibile.

## 5. Una sola run LIVE, un solo modello

25 narrative da `gemma4:cloud`, in un'unica esecuzione. Nessuna misura di
stabilità fra run, nessun confronto fra modelli. Il tasso di successo del
trasporto (25/25) è più alto di quello osservato per il parser (~74 %), ma su un
campione troppo piccolo per trarne una conclusione.

## 6. La rilevazione dei farmaci è morfologica

Le radici INN coprono le classi più comuni in oncologia. Un farmaco con radice
non elencata, o un nome commerciale, potrebbe non essere intercettato se scritto
in minuscolo e se non compare come simbolo maiuscolo. La regola sui simboli
maiuscoli resta il secondo strato.

## 7. Il ramo THERAPY_DISCOVERY non segnala la polarità

Limite ereditato, non introdotto qui: `NEW-01` dell'audit finale. In discovery
`support_direction` è `NOT_APPLICABLE` e il NarratorInput non porta un segnale di
polarità, quindi la narrativa non può dichiararlo. Resta da correggere a monte,
nel gate, non nel Narrator.

## Cosa NON è una limitazione

- il fallback **non** è un fallimento: è l'esito definito quando la verifica non
  passa, e il dossier strutturato resta completo;
- l'assenza di retry semantico è una scelta, non una mancanza;
- il verifier non usa NLP clinico generale per progetto, non per difetto.

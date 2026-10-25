# Frontend V3: prima e dopo

## Prima

- Form condiviso con pipeline legacy e V3.
- Il percorso V3 non esponeva intervention, direction e CaseContext.
- La vista mostrava conteggi, card, bucket e provenance sintetica.
- I separatori JSX introducevano caratteri ? tra campi.
- Il gate trace era collassato e non mostrava caso/claim.
- I record tecnici erano visibili insieme alla provenance ma non avevano una sezione ispettiva propria.

## Dopo

- Form clinico V3 esplicito, con policy e limite coerenti con il request model reale.
- Form legacy mantenuto e separato visivamente.
- Header stabile con record analizzati, claim cliniche, record tecnici, bucket, latenza e versioni.
- Tab coordinate: Dossier clinico, Pipeline, Evidenze, Provenienza, Dati tecnici.
- Stepper verticale con otto stage derivati dalla response.
- Gate trace con stato, reason code, messaggio, valore del caso e valore della claim.
- Score nativo mostrato come punteggio strutturale; null diventa non disponibile, non zero.
- Astensione esplicita quando non esistono primary o warning.
- Narrazione dichiarata non eseguita se non esiste un renderer reale.

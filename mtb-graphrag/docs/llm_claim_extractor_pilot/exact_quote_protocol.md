# Protocollo exact-quote

Una quote valida ? una sottostringa continua, carattere per carattere, di `exact_text`. L?adapter calcola localmente presenza, occorrenze, offset e hash. Una quote assente produce `DROPPED_NO_QUOTE`; una quote ripetuta produce `DROPPED_AMBIGUOUS_OFFSET`. Nessuna correzione semantica viene applicata.

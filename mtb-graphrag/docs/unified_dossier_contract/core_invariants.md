# Core invariants

Prima e dopo l’aggregazione devono restare identici:

- claim IDs e ordine delle claims;
- bucket summary e bucket;
- score;
- gate trace e reason codes;
- ordine delle evidenze e conteggi;
- abstention;
- technical records.

Il builder conserva inoltre hash SHA-256 canonici del core. Ontology shadow,
diagnostic context ed ESCAT sono esclusivamente additivi.

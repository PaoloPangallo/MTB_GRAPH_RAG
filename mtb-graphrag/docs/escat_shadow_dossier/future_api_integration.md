# Integrazione API futura

Una futura API potrebbe aggiungere `clinical_actionability` alla risposta del
dossier come campo opzionale e read-only, mantenendo invariati schema e valori
di evidenze, provenance, bucket, score, gate trace, abstention e ordinamento.

Prima dell’integrazione servirebbero almeno:

- approvazione del contratto di presentazione;
- una sorgente persistente e versionata degli assessment;
- risoluzione deterministica degli assessment concorrenti;
- policy di autenticazione, audit e autorizzazione del curatore;
- promozione separata del ruleset da `RESEARCH_DRAFT` a una versione approvata.

Questa branch non modifica l’endpoint V3.

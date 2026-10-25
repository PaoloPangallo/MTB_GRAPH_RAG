# Modello di regole ESCAT

Una futura regola deve essere un record versionato:

    {
      "rule_id": "...",
      "framework": "ESCAT",
      "framework_version": "...",
      "tier": "...",
      "subtier": "...",
      "requirements": [],
      "source": {
        "identifier": "...",
        "locator": "...",
        "version": "...",
        "date": "..."
      },
      "notes": "...",
      "tests": []
    }

## Stato del repository

Il repository locale contiene il riferimento bibliografico a Mateo et al. in
V3_POSITIONING.md, ma il documento è marcato come da verificare e non contiene
la definizione normativa completa dei tier. Non è quindi possibile creare
regole ESCAT ufficiali senza introdurre conoscenza esterna.

## Regole ammesse nel futuro

Un motore futuro può valutare solo requisiti espliciti e versionati. Deve
distinguere:

- valore ESCAT esplicito dalla fonte;
- regola deterministica derivata;
- evidenza generica CIViC/OncoKB;
- inferenza legacy;
- revisione manuale.

Non è ammesso il mapping automatico evidence_level A/B/C/D -> ESCAT.

# Modello concettuale

Il prototipo espone cinque componenti separati:

- `OntologyConcept`: label, tipo, sinonimi, chiave di registry, eventuale ID canonico e archi locali;
- `OntologyRegistry`: costruisce una vista read-only dagli asset verificati;
- `EntityNormalizer`: case folding, spazi, punteggiatura, alias locali e parsing deterministico di gene/alterazione/fusione;
- `OntologyMatch`: risultato pairwise con tipo, distanza, path, compatibilità candidata e spiegazione;
- `OntologyShadowEvaluator`: esegue il confronto senza modificare l’oggetto claim.

I match ammessi sono `EXACT`, `SYNONYM`, `DESCENDANT`, `ANCESTOR`, `CLASS_MATCH`, `RELATED`, `INCOMPATIBLE`, `UNKNOWN`.

`canonical_id` è valorizzato soltanto quando presente nell’asset locale. La chiave interna `disease:nsclc`, per esempio, è una chiave di registry tracciabile ma non un identificatore ontologico inventato.

La distinzione architetturale è:

```json
{
  "publication_or_concept_linked": true,
  "claim_supported": false,
  "match": {
    "type": "DESCENDANT",
    "path": ["disease:nsclc", "disease:lung adenocarcinoma"],
    "compatible_candidate": true
  }
}
```

`compatible_candidate` è solo un segnale terminologico shadow. Non significa applicabilità clinica, supporto documentale o ammissione.

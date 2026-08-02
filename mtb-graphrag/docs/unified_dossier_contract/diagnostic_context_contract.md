# Diagnostic context contract

I nodi `CompanionDiagnostic` restano record strutturali e non diventano
qualified claim. Possono contenere:

- diagnostic name e biomarker/gene;
- terapia strutturalmente associata;
- tecnologia e specimen;
- disponibilità di fonte, disease e regolatoria;
- graph identifiers e limitazioni.

In assenza di dati vengono dichiarati `disease context missing`, `provenance
missing` e `regulatory status unavailable`. Un’associazione strutturale con
una terapia non implica che la terapia sia richiesta.

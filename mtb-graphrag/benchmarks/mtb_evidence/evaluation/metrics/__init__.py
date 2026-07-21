"""Metriche della catena di valutazione, separate per stadio.

Ogni famiglia misura un passaggio diverso e non deve assorbire gli errori degli
altri:

- `kg_coverage`      quanto del clinical gold esiste nello snapshot;
- `retrieval_fidelity` quanto dello snapshot gold viene recuperato;
- `report_fidelity`  quanto del recuperato sopravvive nel report;
- `applicability`    se cio' che sopravvive e' qualificato correttamente;
- `orchestration`    come il percorso e' stato scelto ed eseguito.
"""

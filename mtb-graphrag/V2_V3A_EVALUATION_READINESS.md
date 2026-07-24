# Readiness del confronto V2 / V3-A

1. **Il retriever è deterministico?** Sì. Due run completi producono file byte-identical e hash identici.
2. **Il corpus fingerprint è verificato?** Sì: `99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd`.
3. **La modalità V2 è riproducibile?** Sì, entro il contratto offline congelato.
4. **Ogni divergenza V2 è spiegata?** Sì. Il report distingue la parity offline dai dettagli di traversal non serializzati.
5. **I qualificatori prototype-only non eliminano risultati?** Sì; una violazione solleva un errore tipizzato.
6. **I risultati invalidi sono conservati nell'audit?** Sì; `ES-V2-evidence-100003` è audit-only con motivo provvisorio.
7. **Evidenza clinica e preclinica restano separate?** Sì, tramite unit type e `evidence_context`.
8. **Risultati negativi restano negativi?** Sì; `does_not_support` non diventa supporto positivo.
9. **Case-level non viene generalizzato?** Sì; warning, penalità prudente e `frequency_inferred=false`.
10. **Mapping pendenti non diventano exact?** Sì; CH5424802/alectinib, CNG/amplification e less-sensitive/resistance restano pending.
11. **Tutti gli score hanno breakdown?** Sì; la somma dei contributi coincide con il totale.
12. **Ogni risultato ha provenance?** Sì; statement, qualification link e sole unità attive.
13. **La configurazione di scoring è congelata?** Sì: `ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00`.
14. **Il clinical gold è stato usato per scegliere i pesi?** No.
15. **Il sistema è pronto per un confronto esplorativo?** Sì, dopo accettazione tecnica.
16. **Il sistema è pronto per una valutazione finale?** No.

## Stati

- `ready_for_exploratory_v2_v3a_comparison`: **true**
- `ready_for_final_v2_v3a_evaluation`: **false**

La valutazione finale resta bloccata perché nessuna unità è `final`, il gold non è valutabile e la seconda revisione indipendente non è stata completata.

Il prossimo passo, soltanto dopo accettazione tecnica, è il confronto esplorativo V2 contro V3-A sul pilot congelato. Non è stato eseguito in questa fase.
# 12 — Limitazioni residue

## Limiti della sorgente, non correggibili in v3

**La struttura dei regimi resta ignota per 572 record.** L'export non contiene il
tipo di interazione fra farmaci. v3 dichiara l'ignoranza invece di mascherarla,
ma non la elimina: 572 candidate non sono eleggibili al match esatto
sull'intervento, e resteranno tali finché la sorgente non porterà quel campo.

**`component_role` vale sempre `UNKNOWN`.** Comparatore, backbone e agente
sequenziale non sono distinguibili.

**`CONTRADICTS_ASSERTION` e `NEUTRAL_OR_NO_DIFFERENCE` non sono mai prodotti.**
`evidence_direction` ha solo `Supports`, `Does Not Support` e vuoto. Una fonte
che contraddicesse attivamente l'asserzione non è distinguibile da una che non la
sostiene.

**Le regole non-Evidence non portano polarità.** 38 688 candidate hanno
`SOURCE_ALIGNMENT_NOT_AVAILABLE`: gene–farmaco, trial e companion diagnostic non
hanno un record di evidenza con una direzione. Non è una perdita di v3 — è
l'assenza del dato.

## Limiti di questo branch, per scelta

**Il match sull'alterazione non è collegato al runtime.**
`evaluate_alteration_expression` è definita e testata ma non chiamata: collegarla
cambierebbe il comportamento del retrieval, fuori dallo scopo.

**Il Pre-Retrieval Eligibility Gate non esiste.** La policy di ammissione è
documentata, non implementata.

**Il default del runtime resta `2.0`.** v3 non è stata validata da un audit
clinico né dai test di regressione end-to-end.

**Nessuna normalizzazione farmacologica.** `BGJ398` e `infigratinib` restano
termini distinti (`KNOWN_DRUG_SYNONYM_GAP`), e un test lo verifica.

**Il fallback OncoKB non è integrato.** L'audit RQ3 precedente resta valido: la
popolazione senza PMID è ancora priva delle chiavi per interrogarlo. v3 **non**
cambia questo: alteration e disease continuano a esistere solo sulle regole
derivate da Evidence.

## Limiti di misura

**La fedeltà è misurata rispetto all'export, non al KG originale.** Un errore già
presente nell'export non sarebbe visibile. Neo4j non è attiva e non fornisce un
secondo riferimento.

**Il campione manuale non è annotato.** 70 record pronti, colonne del revisore
vuote. Senza annotazione, la fedeltà semantica è dimostrata rispetto ai *metadati*
della sorgente, non al giudizio di un esperto.

**Lo strato dei casi ambigui è vuoto.** Il corpus non contiene espressioni non
parsabili né allineamenti incerti. La robustezza del parser su input degeneri è
verificata solo da test sintetici (`BRAF V600E AND` → `MALFORMED_EXPRESSION`), non
da dati reali.

**Il repository v3 pesa 134 MB** contro i 72 MB di v2, per i campi aggiunti
(AST, termini, componenti, polarità raw). È il costo della rappresentazione
esplicita.

## Cosa v3 non afferma

Una GraphCandidateAssertion v3 **non** è: una claim degli autori del paper
citato, un'evidenza documentale, una verità clinica, una raccomandazione, un
supporto verificato.

In particolare `SOURCE_ALIGNED` significa soltanto che il **metadato** della
fonte è coerente con la relazione asserita. Non significa che il testo del paper
la sostenga: quella è la domanda del document grounding, che v3 non anticipa.

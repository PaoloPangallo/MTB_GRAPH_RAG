# Prompt contract 1.3

Il prompt cambia soltanto il contratto delle citazioni. Ogni SourceUnit ? delimitata da `--- SOURCE UNIT START ---`, `source_unit_id`, `unit_type`, `locator`, `exact_text: <<< ... >>>` e `--- SOURCE UNIT END ---`. Solo il testo tra i delimitatori ? citabile.

Il modello deve selezionare prima SourceUnit e quote letterali, poi compilare la tool call flat. Sono vietate parafrasi, traduzioni, ellissi, espansioni, modifiche di punteggiatura o maiuscole e citazioni della candidate. La candidate resta un?ipotesi da verificare.

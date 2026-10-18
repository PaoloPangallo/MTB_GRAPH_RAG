# Guida dei quattro prompt di sistema

La pagina `../Prompt_di_sistema_per_il_relatore.html` è collegata alle edizioni dell’architettura attraverso il pulsante «Prompt di sistema».

Rigenerazione dalla cartella `system_design`:

```powershell
python build-prompts.py --graphviz 'C:\Program Files\Graphviz\bin\dot.exe'
node build.cjs --assemble
python tests/prompts_test.py
```

Il generatore estrae i testi dai sorgenti backend senza importarli né chiamare provider. Per il parser concatena SYSTEM_PROMPT e tutte le aggiunte a TASK_PROMPT. I quattro TXT conservano il testo effettivo; `provenienza.json` ne registra origine, versione, funzione e impronta SHA-256.

`orchestrazione.dot` è il sorgente versionabile della mappa; SVG e PDF sono vettoriali. La pagina incorpora lo SVG e offre i download dei tre formati. L’intera procedura è inclusa in `../export-vectors.ps1`.

Gli esempi distinguono archivio BRAF/NCT, illustrazione del contratto Reader e fixture sintetica AXR1. La revisione documenta il codice presente e non produce nuove esecuzioni dei modelli. La pagina riutilizza la shell grafica dell’audit GCA già generato.

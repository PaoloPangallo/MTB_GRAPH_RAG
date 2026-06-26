import sys
import os
from xhtml2pdf import pisa

def generate_pdf():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {
                size: a4;
                margin: 2.5cm 2cm 2.5cm 2cm;
                @frame header {
                    -pdf-frame-content: header_content;
                    top: 1cm;
                    left: 2cm;
                    right: 2cm;
                    height: 1cm;
                }
                @frame footer {
                    -pdf-frame-content: footer_content;
                    bottom: 1cm;
                    left: 2cm;
                    right: 2cm;
                    height: 1cm;
                }
            }
            
            body {
                font-family: Helvetica, Arial, sans-serif;
                color: #2d3748;
                line-height: 1.6;
                font-size: 10pt;
            }
            
            .header-text {
                font-size: 8pt;
                color: #a0aec0;
                text-align: left;
                border-bottom: 0.5px solid #e2e8f0;
                padding-bottom: 3px;
            }
            
            .footer-text {
                font-size: 8pt;
                color: #a0aec0;
                text-align: right;
                border-top: 0.5px solid #e2e8f0;
                padding-top: 3px;
            }
            
            .title-container {
                text-align: center;
                margin-top: 20px;
                margin-bottom: 40px;
                padding-bottom: 20px;
                border-bottom: 3px double #2b6cb0;
            }
            
            h1 {
                font-size: 22pt;
                color: #1a365d;
                margin: 0;
                font-weight: bold;
                letter-spacing: 0.5px;
            }
            
            .subtitle {
                font-size: 12pt;
                color: #4a5568;
                margin-top: 10px;
                font-style: italic;
            }
            
            .meta-info {
                font-size: 9pt;
                color: #718096;
                margin-top: 5px;
            }
            
            h2 {
                font-size: 14pt;
                color: #2b6cb0;
                margin-top: 25px;
                margin-bottom: 10px;
                border-bottom: 1px solid #2b6cb0;
                padding-bottom: 3px;
                page-break-after: avoid;
            }
            
            h3 {
                font-size: 11pt;
                color: #2d3748;
                margin-top: 15px;
                margin-bottom: 5px;
                font-weight: bold;
                page-break-after: avoid;
            }
            
            p {
                margin: 0 0 10px 0;
                text-align: justify;
            }
            
            ul, ol {
                margin: 0 0 10px 0;
                padding-left: 20px;
            }
            
            li {
                margin-bottom: 5px;
            }
            
            code {
                font-family: Courier, monospace;
                background-color: #edf2f7;
                padding: 1px 3px;
                font-size: 9pt;
                border-radius: 3px;
            }
            
            .code-block {
                font-family: Courier, monospace;
                background-color: #f7fafc;
                border: 1px solid #e2e8f0;
                padding: 10px;
                margin: 10px 0;
                font-size: 8.5pt;
                white-space: pre-wrap;
            }
            
            .highlight-box {
                background-color: #ebf8ff;
                border-left: 4px solid #3182ce;
                padding: 10px 15px;
                margin: 15px 0;
            }
            
            .highlight-box p {
                margin: 0;
                color: #2b6cb0;
                font-weight: 500;
            }
            
            .warning-box {
                background-color: #fffaf0;
                border-left: 4px solid #dd6b20;
                padding: 10px 15px;
                margin: 15px 0;
            }
            
            .warning-box p {
                margin: 0;
                color: #c05621;
                font-weight: 500;
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
                page-break-inside: avoid;
            }
            
            th {
                background-color: #2b6cb0;
                color: white;
                font-weight: bold;
                text-align: left;
                padding: 8px 10px;
                font-size: 9pt;
                border: 1px solid #2b6cb0;
            }
            
            td {
                padding: 8px 10px;
                font-size: 9pt;
                border: 1px solid #e2e8f0;
            }
            
            tr:nth-child(even) {
                background-color: #f7fafc;
            }
            
            .page-break {
                page-break-before: always;
            }
        </style>
    </head>
    <body>
        <!-- Header Content -->
        <div id="header_content" class="header-text">
            Documentazione Tecnica — Pipeline Agentica MTB-GraphRAG v3
        </div>

        <!-- Footer Content -->
        <div id="footer_content" class="footer-text">
            Pagina <pdf:pagenumber> di <pdf:pagecount>
        </div>

        <!-- Cover/Title Block -->
        <div class="title-container">
            <h1>Il Modulo "Complexity Check"</h1>
            <div class="subtitle">Analisi e Architettura del Sistema di Routing Clinico in MTB-GraphRAG</div>
            <div class="meta-info">Documento di Specifica Tecnica • Generato il 22 Giugno 2026</div>
        </div>

        <h2>1. Introduzione e Razionale Clinico</h2>
        <p>
            Il modulo <strong>Complexity Check</strong> rappresenta il punto di ingresso e l'orchestratore decisionale primario della pipeline clinica agentica <strong>MTB-GraphRAG</strong>. 
            Nelle prime iterazioni dell'architettura (v1), il routing era concepito come una mappatura statica basata sulla categoria del benchmark. Questa scelta, tuttavia, presentava notevoli limiti di generalizzabilità in contesti clinici reali.
        </p>
        <p>
            Per superare tale rigidità, a partire dalla versione v2 e consolidandosi nella v3, è stato introdotto il <strong>Complexity Check dinamico guidato da LLM</strong>. La classificazione della complessità del caso clinico in tre livelli (<code>low</code>, <code>moderate</code>, <code>high</code>) persegue tre obiettivi fondamentali:
        </p>
        <ul>
            <li><strong>Ottimizzazione delle Risorse e dei Costi</strong>: Evita l'attivazione di agenti complessi e costosi (come il <code>Trial Matcher</code> o il <code>Resistance Checker</code>) per casi oncologici lineari che presentano soluzioni terapeutiche standard già consolidate in prima linea.</li>
            <li><strong>Riduzione della Latenza</strong>: I casi a bassa complessità seguono una "fast-path" (corsia preferenziale diretta) verso l'agente sintetizzatore (<code>Synthesizer</code>), riducendo drasticamente il tempo di elaborazione del report finale.</li>
            <li><strong>Accuratezza Specialistica</strong>: Consente agli agenti più complessi di focalizzarsi unicamente su scenari complessi (es. mutazioni di resistenza acquisita, biomarker tumor-agnostici, trial clinici di seconda linea o successiva), strutturando la prompt-engineering in modo specifico per la fascia di difficoltà rilevata.</li>
        </ul>

        <h2>2. Integrazione nel Grafo LangGraph</h2>
        <p>
            All'interno del modulo di assemblaggio del grafo (<a href="file:///c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag/backend/pipeline/graph.py">graph.py</a>), il <code>complexity_check</code> è registrato come nodo iniziale ed è collegato direttamente all'entry point <code>START</code>. 
        </p>
        <p>
            L'instradamento successivo avviene tramite un arco condizionale pilotato dalla funzione helper <code>route_by_complexity</code>, che legge lo stato del caso clinico ed effettua la scelta di percorso illustrata nello schema sottostante:
        </p>
        
        <table style="margin-top: 10px;">
            <thead>
                <tr>
                    <th style="width: 25%;">Livello di Complessità</th>
                    <th style="width: 35%;">Nodo Successivo Attivato</th>
                    <th style="width: 40%;">Percorso della Pipeline</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Low</strong></td>
                    <td><code>variant_interpreter_low</code></td>
                    <td>Bypassa Target Identifier e Trial Matcher. Va diretto al <code>synthesizer</code>.</td>
                </tr>
                <tr>
                    <td><strong>Moderate</strong></td>
                    <td><code>variant_interpreter_moderate</code></td>
                    <td>Converte su <code>target_identifier</code>, abilitando l'analisi avanzata e il matching dei trial.</td>
                </tr>
                <tr>
                    <td><strong>High</strong></td>
                    <td><code>variant_interpreter_high</code></td>
                    <td>Converte su <code>target_identifier</code>, abilitando l'analisi avanzata, trial clinici e profili di resistenza complessi.</td>
                </tr>
            </tbody>
        </table>

        <div class="page-break"></div>

        <h2>3. Architettura Logica del Modulo</h2>
        <p>
            Il processo di valutazione della complessità implementato in <a href="file:///c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag/backend/pipeline/agents/complexity_check.py">complexity_check.py</a> si articola in tre fasi sequenziali:
        </p>
        
        <h3>Fase 3.1: Pre-query al Knowledge Graph (Neo4j)</h3>
        <p>
            Prima di invocare il modello di linguaggio, la pipeline esegue una query esplorativa sul database a grafi Neo4j per raccogliere dati grezzi sul livello di evidenze associate all'alterazione genica del paziente. Il tipo di query viene adattato dinamicamente a seconda dell'alterazione (<code>alteration_type</code>) fornita in input:
        </p>
        <ul>
            <li><strong>Mutazione puntiforme (<code>point_mutation</code>)</strong>: Esegue la query <code>CYPHER_PRE_POINT</code> basandosi su gene specifico, variante ed elenco di parole chiave associate al tumore del paziente (<code>disease_keywords</code>).</li>
            <li><strong>Biomarker generico (<code>biomarker</code>)</strong>: Esegue <code>CYPHER_PRE_BIOMARKER</code> per identificare profili quali <i>MSI High</i> o <i>TMB High</i>.</li>
            <li><strong>Altre alterazioni (CNA, Fusioni, ecc.)</strong>: Esegue <code>CYPHER_PRE_MP</code>, calcolando preventivamente la keyword dell'alterazione molecolare tramite la funzione di utilità <code>get_mp_keyword</code>.</li>
        </ul>
        <p>
            La query estrae metriche strutturate relative a:
            <ol>
                <li>Numero totale di evidenze cliniche di livello A o B (linee guida o forti evidenze cliniche).</li>
                <li>Gradi di significatività clinica registrati (<code>significances</code>).</li>
                <li>Numero di trial clinici attivi mappati sul grafo per quella specifica combinazione patologia-gene.</li>
            </ol>
        </p>

        <h3>Fase 3.2: Valutazione LLM (Prompt Decisionale)</h3>
        <p>
            I dati clinici primari dell'input (gene, variante, tipo di tumore, linea terapeutica) vengono formattati insieme alle metriche estratte dal KG e inviati a un LLM. Il modello viene istruito con un prompt di sistema rigido (<code>COMPLEXITY_SYSTEM</code>) per operare come classificatore oncologico:
        </p>
        
        <div class="code-block">
Criteri di Classificazione LLM:
- LOW: Evidenze dirette A/B presenti, nessuna resistenza nota, nessun trial clinico rilevante,
       paziente in prima linea terapeutica, variante puntiforme con evidenza diretta.
- MODERATE: Drug matching non immediato, richiesta di companion diagnostic,
            oppure presenza di profili di resistenza nelle evidenze, oppure alterazioni
            di tipo fusione/CNA/varianti atipiche.
- HIGH: Trial clinici attivi rilevanti, profilo di resistenza acquisita presente,
        terapia di seconda linea o successiva, oppure biomarker tumor-agnostico.
        </div>

        <h3>Fase 3.3: Regole di Sanity Check (Override Deterministico)</h3>
        <p>
            Per garantire la sicurezza clinica e prevenire errori di classificazione del modello di linguaggio (ad esempio allucinazioni o risposte "low" su casi clinicamente delicati), il codice esegue un post-processing deterministico per applicare dei livelli minimi di complessità:
        </p>
        
        <div class="warning-box">
            <p><strong>Regole di Override di Sicurezza (Sanity Checks):</strong></p>
            <ul style="margin-top: 5px; margin-bottom: 0px;">
                <li><strong>Biomarker Tumor-Agnostici</strong>: Se il tipo di alterazione è un <code>biomarker</code> (es. MSI, TMB) e l'LLM restituisce "low", la complessità viene forzata a <code>high</code>. I biomarker tumor-agnostici implicano percorsi clinici complessi.</li>
                <li><strong>Linee di Terapia Avanzate</strong>: Se la linea terapeutica in input è <code>second-line</code> o <code>later-line</code> e la risposta è "low", il tier viene elevato a <code>moderate</code>. La progressione tumorale richiede un'analisi terapeutica più approfondita.</li>
                <li><strong>Casi EGFR (Profilo di Resistenza Acquisita)</strong>: Se l'alterazione riguarda il gene <strong>EGFR</strong> ed è classificata come "low", viene forzata a <code>moderate</code>. Questo garantisce che il caso non bypassi il modulo <code>Resistance Checker</code>, essenziale per valutare mutazioni di resistenza acquisita (es. T790M o C797S).</li>
            </ul>
        </div>

        <h2>4. Conclusioni</h2>
        <p>
            Il modulo <strong>Complexity Check</strong> unisce la potenza decisionale e flessibile del modello linguistico (LLM) alla sicurezza e precisione di controlli deterministici basati su regole cliniche ed evidenze strutturate del Knowledge Graph.
            Questa architettura ibrida permette di guidare l'elaborazione del report MTB riducendo i costi e massimizzando l'accuratezza dove è realmente richiesto un approfondimento specialistico.
        </p>
    </body>
    </html>
    """
    
    output_filename = "c:\\Users\\paolo\\Desktop\\IspezioneDatasetTesi\\Complexity_Check_Report.pdf"
    
    with open(output_filename, "w+b") as result_file:
        pisa_status = pisa.CreatePDF(
            html_content,
            dest=result_file
        )
        
    if pisa_status.err:
        print(f"Errore durante la generazione del PDF: {pisa_status.err}")
        sys.exit(1)
    else:
        print(f"PDF generato con successo in: {output_filename}")

if __name__ == "__main__":
    generate_pdf()

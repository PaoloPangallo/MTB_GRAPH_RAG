"""Build the offline guide from explanatory copy and literal backend prompts."""
from __future__ import annotations

import ast
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import subprocess
from prompt_examples import EXPLANATIONS, load_examples

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BACKEND = ROOT / 'mtb-graphrag/backend/research_pipeline'


def literals(path: Path) -> dict:
    """Read string assignments, including every incremental TASK_PROMPT addition."""
    result = {}
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = value
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            if isinstance(node.op, ast.Add) and node.target.id in result:
                result[node.target.id] += ast.literal_eval(node.value)
    return result


def paragraph(text: str) -> str:
    return '<p>' + text + '</p>'


def table(headers, rows):
    head = ''.join('<th scope="col">' + escape(x) + '</th>' for x in headers)
    body = ''.join('<tr>' + ''.join(
        ('<th scope="row">' if i == 0 else '<td>') + escape(value) +
        ('</th>' if i == 0 else '</td>') for i, value in enumerate(row)) + '</tr>' for row in rows)
    return '<div class="table-scroll"><table class="audit-table"><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>'


ROLES = [
    ('parser', 'Case Parser: dal testo al caso strutturato', 'casecontext/prompt.py',
     'Comprensione del caso',
     'Conserva le menzioni cliniche esplicite e le loro citazioni letterali. Associa ogni gene alla propria alterazione e distingue il trattamento oggetto della domanda da quelli precedenti o correnti.',
     'Separare l’estrazione dall’identificazione permette di mantenere visibili le parole originali. Il codice verifica gli ancoraggi e risolve successivamente le entità verso gli identificativi utilizzati dal grafo.',
     'Testo clinico → menzioni con citazioni → controllo degli ancoraggi → risoluzione delle entità → ricerca delle associazioni candidate.',
     'Nel caso sintetico BRAF documentato compaiono melanoma metastatico, BRAF V600K e dabrafenib e trametinib come intervento oggetto della ricerca. La malattia conserva il qualificatore metastatico; gene e variante restano collegati. Il ruolo TARGET descrive la domanda e mantiene distinta l’informazione sull’effettiva somministrazione.',
     'Una menzione ambigua conserva la propria incertezza; un valore assente rimane null o una lista vuota. Il controllo delle citazioni rende ogni campo riconducibile al testo di ingresso.'),
    ('reader', 'Reader: dalla fonte a un’osservazione citabile', 'enrichment/prompt_v3.py',
     'Analisi delle fonti',
     'Legge le source unit selezionate e restituisce un’osservazione documentale con citazione, oppure ABSTAIN. La relazione candidata orienta la ricerca; il contenuto della fonte determina ciò che viene osservato.',
     'Il compito circoscritto rende espliciti popolazione, profilo molecolare, combinazione farmacologica e tipo di affermazione. Le unità di contesto aiutano la lettura e restano distinte dalle unità usate come evidenza.',
     'Relazione candidata + caso + source unit → osservazione e citazione → autenticazione della citazione e controlli sulla relazione.',
     'Per la pubblicazione PMID 28891408, l’esempio archiviato riguarda una fonte su terapia adiuvante nello stadio III e varianti V600E o V600K. La citazione risulta autentica; il confronto con il caso metastatico rimane un controllo distinto. L’esito documentato è NO_SUPPORT per una relazione della famiglia EVIDENCE_STATEMENT.',
     'Il Reader può astenersi quando il contenuto utile è insufficiente. L’autenticità della citazione e l’ammissione della relazione sono valutazioni successive e separate.'),
    ('semantica', 'Confronto semantico: che cosa sostiene davvero il passaggio?', 'enrichment/semantic_alignment.py',
     'Verifiche, su un ramo condizionale',
     'Confronta il bersaglio della relazione con una proposizione ancorata alla fonte. Descrive direzione, ruolo dell’evidenza, ambito molecolare, popolazione, intervento e tipo di inferenza.',
     'Un passaggio può parlare dello stesso farmaco e dello stesso gene, ma descrivere criteri di arruolamento anziché un risultato osservato. Il contratto rende queste differenze leggibili e consente al codice di applicare una politica di ammissione esplicita.',
     'Osservazione accettata + controlli strutturali PASS + relazione evidenza–farmaco → confronto semantico → verifica degli span letterali → decisione deterministica.',
     'Il test di contratto usa la frase sintetica «AXR1 mutation showed sensitivity to agent-x in lung cancer.» Con risultato osservato, affermazione diretta, ambiti SAME e certezza ESTABLISHED, il test attende DOCUMENT_SUPPORTED. Un ambito molecolare o di popolazione NARROWER conduce a PARTIALLY_SUPPORTED nelle condizioni previste. Cambiare il ruolo in STUDY_DESIGN conduce a UNVERIFIABLE. Sono casi di test del contratto, distinti dai risultati BRAF e da una misura di accuratezza clinica.',
     'Il ramo attuale riguarda EVIDENCE_DRUG e richiede un’osservazione accettata e controlli strutturali superati. Le altre famiglie seguono i propri validatori. SAME, OPPOSITE, NO_SUPPORT, INSUFFICIENT e AMBIGUOUS restano distinti; errori e indisponibilità del verificatore hanno esiti dedicati.'),
    ('narratore', 'Dossier Narrator: dal dossier alla spiegazione', 'narrative/prompt.py',
     'Presentazione, dopo la costruzione del dossier',
     'Riceve il contenuto ammesso del dossier e scrive una sintesi in italiano: domanda, relazioni, osservazioni delle fonti, controlli e limiti. Il prompt è in inglese e assegna esplicitamente la spiegazione dei dati ricevuti.',
     'La generazione permette di collegare le informazioni in una spiegazione leggibile. Il modello conserva le decisioni del dossier e attribuisce ogni osservazione alla sua fonte; il codice verifica il risultato prima della presentazione.',
     'Dossier → proiezione dei contenuti ammessi → spiegazione generata → verificatore della narrazione → presentazione o ripiego deterministico verificato.',
     'Per una voce BRAF il modello riceve la relazione ricercata, le osservazioni conservate, le fonti e gli esiti dei controlli. Deve spiegare il collegamento fra questi elementi conservando limiti e incertezza. Il bersaglio del grafo resta distinto dall’osservazione letta nella fonte. Le prove dedicate riportano separatamente risposte del modello, rifiuti e ripieghi.',
     'Il verificatore controlla identità e copertura, citazioni, entità, fonti, quantità, stati, polarità, raccomandazioni e limiti critici riconoscibili. Un superamento attesta conformità a queste regole: la prosa libera conserva un limite di verifica semantica. In caso di rifiuto viene verificato separatamente il testo deterministico; il dossier rimane disponibile.'),
]


def build(graphviz: str = 'C:/Program Files/Graphviz/bin/dot.exe'):
    output = HERE / 'prompt-sistema'
    output.mkdir(exist_ok=True)
    sections, provenance = [], []
    examples = load_examples(ROOT)
    for key, title, relative, placement, task, why, flow, example, controls in ROLES:
        path = BACKEND / relative
        values = literals(path)
        version = values.get('PROMPT_VERSION', values.get('NARRATOR_PROMPT_VERSION'))
        effective = values['SYSTEM_PROMPT']
        if key == 'parser':
            effective += '\n' + values['TASK_PROMPT']
        filename = key + '.txt'
        (output / filename).write_text(effective, encoding='utf-8')
        provenance.append({'role': key, 'source': path.relative_to(ROOT).as_posix(),
                           'source_sha256': sha256(path.read_bytes()).hexdigest(),
                           'prompt_sha256': sha256(effective.encode()).hexdigest(),
                           'version': version, 'tool': values['TOOL_NAME']})
        lesson = EXPLANATIONS[key]
        response = examples[key]
        answer = '<div class="prompt-response"><h3>Esempio di risposta</h3>' + paragraph(escape(response['label']))
        if response.get('rows'):
            answer += table(['Informazione restituita', 'Risposta'], response['rows'])
        if response.get('quotation'):
            answer += paragraph('Citazione conservata dalla fonte:') + '<blockquote>' + escape(response['quotation']) + '</blockquote>'
        if response.get('response_text'):
            for card in response.get('source_cards') or []:
                answer += source_card_html(card)
            answer += '<blockquote>' + escape(response['response_text']) + '</blockquote>'
        answer += paragraph(escape(response['meaning'])) + '</div>'
        sections.append('<section id="' + key + '"><h2>' + title + '</h2>' +
                        paragraph('<strong>Posizione:</strong> ' + placement + '.') +
                        paragraph(lesson['task']) + '<h3>Perché serve</h3>' + paragraph(lesson['why']) +
                        '<p class="prompt-flow">' + escape(lesson['flow']) + '</p>' +
                        '<h3>Che cosa riceve nell’esempio</h3>' + paragraph(escape(response['input'])) + answer +
                        '<h3>Che cosa accade dopo la risposta</h3>' + paragraph(lesson['controls']) +
                        '<details><summary>Approfondimento: prompt originale e dettagli del codice</summary>' +
                        paragraph(example) + paragraph(controls) +
                        paragraph('Funzione: <code>' + escape(values['TOOL_NAME']) +
                                  '</code>. Versione del prompt: ' + escape(version) + '.') +
                        paragraph('Sorgente: <code>' + escape(path.relative_to(ROOT).as_posix()) + '</code>.') +
                        '<pre><code>' + escape(effective) + '</code></pre>' +
                        '<a href="prompt-sistema/' + filename + '" download>Scarica il prompt completo · TXT</a></details></section>')

    dot = '''digraph prompts {
graph [rankdir=TB,bgcolor="transparent",pad="0.3",nodesep="0.35",ranksep="0.55"];
node [shape=box,style="rounded,filled",fillcolor="#e7f2ef",color="#92b5ae",fontname="Arial",fontsize=17,margin="0.22,0.16"];
edge [color="#628078",fontname="Arial",fontsize=13];
case [label="Testo clinico"];
parser [label="Case Parser\\nMenzioni e citazioni letterali",fillcolor="#d9ece8"];
retrieve [label="Codice: riconoscimento delle entità e recupero GCA\\nFonti e passaggi da leggere"];
reader [label="Reader\\nOsservazione + citazione, oppure astensione",fillcolor="#d9ece8"];
checks [label="Codice: autenticazione e controlli sulla relazione"];
semantic [label="Confronto semantico\\nDirezione, ambiti e ruolo dell’evidenza",fillcolor="#eee9f4"];
dossier [label="Codice: decisione e dossier\\nOsservazioni, controlli, provenienza e limiti"];
narrator [label="Dossier Narrator\\nUna spiegazione per osservazione\\nConfronto tra studi della stessa relazione",fillcolor="#d9ece8"];
verify [label="Codice: copertura e fedeltà\\nSchede esatte · ogni osservazione spiegata\\nPresentazione / ripiego verificato / dossier"];
case -> parser -> retrieve -> reader -> checks;
checks -> semantic [label="evidenza–farmaco: osservazione e struttura accettate"];
semantic -> dossier;
checks -> dossier [label="altre famiglie: validatori dedicati\nrami non ammessi al confronto: esito del controllo"];
retrieve -> dossier [label="sola provenienza KG",style=dashed];
retrieve -> checks [label="registro: percorso opzionale con dati strutturati",style=dashed];
dossier -> narrator [label="presentazione opzionale"];
narrator -> verify;
}'''
    (output / 'orchestrazione.dot').write_text(dot, encoding='utf-8')
    for fmt in ('svg', 'pdf'):
        subprocess.run([str(graphviz), '-T' + fmt, str(output / 'orchestrazione.dot'),
                        '-o', str(output / ('orchestrazione.' + fmt))], check=True)
    svg = (output / 'orchestrazione.svg').read_text(encoding='utf-8')
    svg = svg[svg.index('<svg'):]
    intro = '<h1>I quattro prompt di sistema</h1>' + paragraph(
        'Quattro ruoli accompagnano il percorso dal caso clinico alla presentazione. '
        'Per ciascuno vediamo che cosa riceve, quale compito svolge e come risponde. '
        'Il codice collega i passaggi e controlla i risultati prima di utilizzarli.') + paragraph(
        '<a href="Prove_narratore_per_il_relatore.html">Leggi le prove effettive del narratore</a> · '
        '<a href="Audit_semantico_del_dossier.html">Valutazione semantica delle spiegazioni</a> · '
        '<a href="prompt-sistema/narratore.txt" download>Scarica il prompt del narratore in inglese</a>')
    nav = '<nav class="audit-nav" aria-label="Sezioni prompt">' + ''.join(
        '<a href="#' + key + '">' + label + '</a>' for key, label in [
            ('mappa', 'Posizione nell’architettura'), ('parser', 'Case Parser'),
            ('reader', 'Reader'), ('semantica', 'Confronto semantico'),
            ('narratore', 'Narratore'), ('coordinamento', 'Come lavorano insieme'),
            ('percorsi', 'Casi d’uso'), ('punti-forza', 'Punti di forza'),
            ('provenienza', 'Riferimenti degli esempi')]) + '</nav>'
    overview = ('<section id="mappa"><h2>Dove intervengono i modelli</h2>' + paragraph(
        'Le sei macrofasi rimangono la struttura principale: comprensione del caso, recupero GCA, '
        'analisi delle fonti, verifiche, dossier e presentazione. Il codice organizza la ricerca e '
        'costruisce il dossier. I quattro prompt aiutano a comprendere il caso, leggere le fonti, '
        'confrontare il significato delle affermazioni e spiegare i risultati.') +
        '<figure>' + svg + '<figcaption>Le caselle indicano esplicitamente il componente responsabile. '
        'Il confronto semantico segue una condizione; la presentazione è opzionale. '
        '<a href="prompt-sistema/orchestrazione.dot" download>DOT</a> · '
        '<a href="prompt-sistema/orchestrazione.svg" download>SVG</a> · '
        '<a href="prompt-sistema/orchestrazione.pdf" download>PDF vettoriale</a></figcaption></figure></section>')
    tools = ('<section id="tool-call"><h2>Che cosa significa tool call in questa architettura</h2>' + paragraph(
        'Il codice invia al modello un messaggio di sistema, i dati del compito e lo schema della funzione attesa. '
        'La risposta contiene il nome della funzione e i suoi argomenti strutturati. '
        'Il codice esegue recupero e verifiche; il modello restituisce gli argomenti del contratto assegnato.') + table(
            ['Componente', 'Funzione richiesta', 'Contenuto della risposta'], [
                ['Case Parser', 'submit_case_context', 'Menzioni cliniche, citazioni, ruoli e intento della domanda'],
                ['Reader', 'submit_paper_relation_observation', 'QUOTE con osservazione e citazione, oppure ABSTAIN'],
                ['Confronto semantico', 'submit_semantic_alignment', 'Allineamento, ambiti, ruolo dell’evidenza e span letterali'],
                ['Dossier Narrator', 'emit_dossier_narrative', 'Sintesi, testo per ogni candidate_id, limiti e chiusura']]) +
        '<h3>Un esempio di risposta strutturata</h3>' + paragraph(
            'Esempio didattico minimale del Reader: l’astensione indica che il materiale fornito è insufficiente '
            'a produrre un’osservazione citabile. È una forma del contratto, distinta da un esito misurato sul caso BRAF.') +
        '<pre><code>' + escape(json.dumps({'name': 'submit_paper_relation_observation',
            'arguments': {'decision': 'ABSTAIN', 'abstain_reason': 'NO_RELEVANT_EVIDENCE'}}, indent=2)) + '</code></pre>' +
        paragraph('Nel protocollo della risposta, questi dati si trovano in <code>tool_calls[].function</code>; '
                  '<code>arguments</code> viene normalmente serializzato come stringa JSON. Qui è aperto come oggetto per facilitarne la lettura.') +
        '<details><summary>Formato, recuperi e orchestrazione delle chiamate</summary>' + paragraph(
            'Il trasporto configura tools e tool_choice con la funzione attesa e valida nome, numero di chiamate, '
            'JSON e schema. È previsto anche il recupero di un oggetto JSON completo dalla risposta testuale, '
            'purché soddisfi il contratto. I recuperi di formato mantengono separata la correzione strutturale dal giudizio sul contenuto.') +
        paragraph('Il Case Parser ha tentativi mirati per errori di formato; il trasporto gestisce recuperi limitati '
                  'per formato e problemi infrastrutturali. Il narratore può suddividere lotti problematici e richiede '
                  'copertura completa delle relazioni. Budget, configurazione e disponibilità del provider governano le chiamate effettive.') +
        paragraph('Il confronto semantico riceve il bersaglio e l’evidenza ancorata; il verdetto e la confidenza del Reader '
                  'restano separati dal suo ingresso. Il narratore riceve invece il contenuto della proiezione del dossier; '
                  'il verificatore confronta la spiegazione con questi dati attraverso controlli deterministici. Il catalogo precostruito resta il ripiego verificabile esattamente.') + '</details></section>')
    routes = ('<section id="percorsi"><h2>Tre percorsi delle fonti, impieghi diversi</h2>' + table(
        ['Percorso', 'Uso dei prompt', 'Esempio e interpretazione'], [
            ['Pubblicazione', 'Parser; Reader sui passaggi selezionati; confronto semantico se il ramo lo richiede; narratore opzionale',
             'PMID 28891408: citazione autentica e osservazione sul contesto adiuvante. La famiglia EVIDENCE_STATEMENT segue il proprio validatore.'],
            ['Registro, percorso predefinito', 'Il Reader legge il materiale di registro predisposto per l’analisi',
             'Disegno, popolazione e criteri descrivono lo studio. L’eleggibilità individuale richiede una valutazione dedicata.'],
            ['Registro, configurazione opzionale focused-v1', 'I fatti strutturati di un NCT risolto possono alimentare il percorso dedicato',
             'NCT02279004 nell’esempio archiviato: fatti strutturati, zero chiamate generative al Reader, eleggibilità NOT_EVALUATED.'],
            ['Sola provenienza nel Knowledge Graph', 'Il dossier conserva la provenienza disponibile nel grafo; il narratore rimane opzionale',
             'L’associazione FoundationOne CDx–BRAF dell’esempio rimane una relazione del grafo con il proprio limite documentale.']]) + paragraph(
        'Il Case Parser riguarda il caso complessivo. La tabella descrive le chiamate documentali successive: '
        'il numero delle chiamate dipende dalle fonti selezionate, dai rami attivati e dai budget disponibili.') + '</section>')
    strengths = ('<section id="punti-forza"><h2>Perché distribuire il lavoro fra quattro prompt</h2>' + table(
        ['Scelta architetturale', 'Vantaggio concreto', 'Controllo che la rende utile'], [
            ['Compiti circoscritti', 'Ogni passaggio ha ingressi e uscite riconoscibili', 'Schemi distinti e responsabilità esplicite'],
            ['Ancoraggio al testo', 'Menzioni e osservazioni sono riconducibili alla fonte', 'Citazioni letterali, identità delle source unit e verifica degli span'],
            ['Giudizi separati', 'Una citazione autentica può restare fuori dall’evidenza ammessa', 'Autenticazione, controlli strutturali e ammissione distinti'],
            ['Confronto semantico condizionale', 'Il confronto approfondito segue il tipo di relazione', 'Condizioni del ramo e politica deterministica di ammissione'],
            ['Generazione e ripiego distinti', 'Il modello spiega il dossier e conserva le attribuzioni', 'Regole di fedeltà sulla prosa; confronto esatto per il ripiego precostruito']]) + paragraph(
        'Queste proprietà descrivono il progetto e i controlli implementati. La qualità scientifica del contenuto '
        'si valuta con protocolli e dati di riferimento dedicati; i test di contratto verificano il comportamento delle regole.') + '</section>')
    evidence = ('<section id="provenienza"><h2>Sorgenti, esempi e possibilità di verifica</h2>' + paragraph(
        'I prompt integrali sono estratti dai file Python presenti nel progetto. Per il Case Parser il testo effettivo '
        'comprende SYSTEM_PROMPT e tutte le aggiunte a TASK_PROMPT. Gli esempi BRAF e NCT provengono '
        'dagli esempi documentati dell’atlante; la frase AXR1 è una fixture di test. Questa pagina documenta il codice '
        'e gli archivi disponibili e viene costruita senza nuove chiamate ai modelli.') + paragraph(
        'Il quarto ruolo attualmente collegato al provider live è il narratore del dossier tramite emit_dossier_narrative. '
        'Il selettore di varianti emit_narrative_plan rimane disponibile nel progetto; il catalogo deterministico serve come ripiego distinto dalla generazione.') +
        table(['Aspetto', 'Sorgente nel backend'], [
            ['Collegamento dei provider', 'live_providers.py'],
            ['Tool call e formato', 'enrichment/transport.py'],
            ['Contratto semantico', 'enrichment/semantic_contract.py; tests/test_semantic_admission_contract.py'],
            ['Narrazione e verifica di fedeltà', 'narrative/narrator.py; narrative/verifier.py; narrative/stage_runner.py; narrative/controlled.py']]) +
        '<a href="prompt-sistema/provenienza.json" download>Riferimenti, versioni e impronte dei prompt · JSON</a> · '
        '<a href="build-prompts.py" download>Generatore versionabile</a></section>')
    tools = ('<section id="coordinamento"><h2>Come lavorano insieme</h2>' + paragraph(
        'Ogni prompt svolge un compito circoscritto. Il codice prepara le informazioni da inviare, '
        'raccoglie la risposta e applica i controlli previsti prima del passaggio successivo.') + table(
            ['Componente', 'Che cosa restituisce'], [
                ['Case Parser', 'Le informazioni del caso, collegate al testo originale'],
                ['Reader', 'Un’osservazione della fonte con citazione, oppure un’astensione'],
                ['Confronto semantico', 'Il confronto tra la relazione cercata e ciò che afferma la fonte'],
                ['Dossier Narrator', 'Una spiegazione del dossier, con osservazioni, controlli e limiti']]) +
        '<details><summary>Approfondimento: risposte strutturate e tool call</summary>' +
        tools.replace('id="tool-call"', 'id="tool-call-dettaglio"') + '</details></section>')
    routes = ('<section id="percorsi"><h2>Come cambia il lavoro secondo la fonte</h2>' + table(
        ['Fonte', 'Percorso'], [
            ['Pubblicazione', 'Il Reader legge i passaggi selezionati. Le verifiche stabiliscono come conservare l’osservazione nel dossier.'],
            ['Registro di studio · percorso predefinito', 'Il Reader descrive il contenuto del registro. Disegno dello studio, risultati ed eleggibilità individuale mantengono significati distinti.'],
            ['Registro di studio · percorso opzionale', 'Per uno studio già identificato, i dati strutturati del registro possono alimentare il percorso dedicato. L’esempio archiviato segue questa opzione.'],
            ['Solo Knowledge Graph', 'Il dossier conserva la relazione e la sua origine nel grafo, insieme al limite documentale disponibile.']]) +
        paragraph('Il narratore presenta ciò che è stato conservato nel dossier, mantenendo riconoscibile l’origine delle informazioni.') +
        '<details><summary>Approfondimento: esempi e configurazioni</summary>' +
        routes.replace('id="percorsi"', 'id="percorsi-dettaglio"') + '</details></section>')
    strengths = strengths.replace('Schemi distinti e responsabilità esplicite', 'Compiti e risposte chiaramente distinti').replace(
        'verifica degli span', 'verifica dei passaggi citati').replace(
        'Condizioni del ramo e politica deterministica di ammissione', 'Controlli preliminari e regole esplicite per conservare l’evidenza')
    evidence = evidence.replace('<h2>Sorgenti, esempi e possibilità di verifica</h2>',
        '<h2>Riferimenti degli esempi</h2>' + paragraph(
            'Le risposte del parser e del Reader provengono dall’archivio del caso BRAF. '
            'La risposta del narratore è estratta da una prova effettiva. Il confronto semantico '
            'usa un caso sintetico dei test, presentato come risposta attesa.') +
        '<a href="prompt-sistema/esempi-risposte.json" download>Scarica gli esempi e i loro riferimenti</a>' +
        '<details><summary>Sorgenti e dettagli di verifica</summary>').replace('</section>', '</details></section>')
    base = (HERE / 'Audit_GCA_per_il_relatore.html').read_text(encoding='utf-8')
    main = '<main class="audit-main" id="main">' + intro + nav + overview + ''.join(sections) + tools + routes + strengths + evidence + '</main>'
    page, count = re.subn(r'<main class="audit-main" id="main">.*?</main>', lambda _: main, base, flags=re.S)
    assert count == 1
    page = page.replace('<title>Audit GCA · struttura e corpus</title>', '<title>I quattro prompt di sistema · Architettura</title>')
    page = page.replace('Stampa audit', 'Stampa guida')
    page = page.replace('</style>', '.prompt-flow{padding:18px 22px;background:#e7f2ef;border:1px solid #b6cec8;border-radius:8px;line-height:1.8}.prompt-response{margin:26px 0;padding:22px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}.prompt-response>p:first-of-type{font-size:13px;color:var(--muted)}.prompt-response blockquote{font-family:Georgia,serif;font-size:17px;line-height:1.8;margin:22px 0;padding:20px 24px;background:white;border:1px solid var(--rule);border-radius:10px;max-width:75ch}.audit-main pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:18px;background:#f4f7f6;font-size:13px}.audit-main p{max-width:75ch}@media(max-width:700px){.prompt-response blockquote{padding:16px;font-size:16px}}@media print{details{display:block}details pre{font-size:8pt}}' + '</style>', 1)
    (HERE / 'Prompt_di_sistema_per_il_relatore.html').write_text(page, encoding='utf-8')
    (output / 'provenienza.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'esempi-risposte.json').write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding='utf-8')
    test_source = ROOT / 'mtb-graphrag/evaluation/dossier_narration_ten_final/results.json'
    if test_source.is_file():
        render_test_report(base, test_source)
    print('Guida dei quattro prompt: HTML, testi integrali, provenienza, DOT, SVG e PDF.')


def source_card_html(card):
    identity = card.get('public_source_identity') or card.get('paper_id') or 'Fonte'
    label = escape(identity)
    if card.get('url'):
        label = '<a href="' + escape(card['url'], quote=True) + '">' + label + '</a>'
    return ('<div class="prompt-response source-card"><h3>Scheda della fonte</h3>' +
            paragraph('<strong>' + escape(card.get('title') or identity) + '</strong>') +
            paragraph(label + (' · ' + escape(card['journal']) if card.get('journal') else '')) +
            ('<blockquote>' + escape(card['validated_quote']) + '</blockquote>'
             if card.get('validated_quote') else paragraph('Citazione autenticata disponibile nella scheda: assente.')) + '</div>')


def documented_narration_html():
    source = ROOT / 'mtb-graphrag/evaluation/source_first_narrator_v45/results.json'
    report = json.loads(source.read_text(encoding='utf-8'))
    rows = report['cases']
    passed = sum(row['verification']['status'] == 'PASS' for row in rows)
    html = '<section><h2>Dalle fonti alla spiegazione del caso BRAF</h2>' + paragraph(
        'Tre prove su voci di un dossier di ricerca archiviato. Ogni scheda conserva titolo, identificativo pubblico '
        'e citazione autenticata; il modello riceve questi dati e ne spiega il contenuto in italiano. '
        'I metadati bibliografici provengono dalla cache documentata.') + paragraph(
        f'{passed} risposte su {len(rows)} superano i controlli implementati. '
        'La verifica confronta le schede esattamente con l’ingresso e controlla vincoli sulla prosa. '
        'Il giudizio scientifico e l’applicabilità clinica richiedono una valutazione dedicata.')
    for row in rows:
        narrative = row['call'].get('narrative')
        html += '<section><h3>' + escape(row['name'].replace('BRAF_', 'Pubblicazione PMID ')) + '</h3>'
        html += paragraph(escape(row['narrator_input'].get('case_overview', '')))
        for candidate in row['narrator_input']['candidates']:
            for card in candidate.get('source_cards') or []:
                html += source_card_html(card)
        html += paragraph('Esito dei controlli: <strong>' + escape(row['verification']['status']) + '</strong>.')
        if narrative:
            accepted = row['verification']['status'] == 'PASS'
            html += ('<h3>Spiegazione del modello</h3>' if accepted else
                     '<details><summary>Risposta respinta: testo e motivi</summary>')
            for entry in narrative['candidate_narratives']:
                html += paragraph(escape(entry['text']))
            for key in ('limitations_summary', 'closing_note'):
                if narrative.get(key):
                    html += paragraph(escape(narrative[key]))
            if not accepted:
                html += paragraph(escape(', '.join(row['verification']['reason_codes']))) + '</details>'
        html += '</section>'
    html += paragraph('<a href="verifica/narratore-fonti-documentate.json" download>Ingressi, fonti, risposte e controlli · JSON</a>') + '</section>'
    (HERE / 'verifica/narratore-fonti-documentate.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return html


def observation_facts_html(observation):
    observed = observation.get('observed') or {}
    labels = {'disease': 'Popolazione / malattia', 'intervention': 'Intervento osservato',
              'finding': 'Risultato riportato nella fixture', 'subjects': 'Profilo molecolare',
              'uncertainty': 'Incertezza registrata', 'caveats': 'Limiti dell’osservazione',
              'conflict_markers': 'Contrasti registrati'}
    rows = []
    for key, label in labels.items():
        value = observed.get(key)
        if value in (None, '', [], {}):
            continue
        if key == 'subjects':
            value = ', '.join(str(item.get('surface_value') or item.get('canonical_value') or '') for item in value)
        elif isinstance(value, list):
            value = '; '.join(str(item) for item in value)
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        rows.append([label, str(value)])
    html = table(['Informazione conservata', 'Dato dell’osservazione'], rows) if rows else ''
    html += '<details><summary>Dati completi dell’osservazione e controlli registrati</summary><pre>' + escape(
        json.dumps(observation, ensure_ascii=False, indent=2)) + '</pre></details>'
    return html


def multistudy_narration_html():
    source = ROOT / 'mtb-graphrag/evaluation/multistudy_narrator_v51_verified/results.json'
    report = json.loads(source.read_text(encoding='utf-8'))
    rows = report['cases']
    passed = sum(row['verification']['status'] == 'PASS' for row in rows)
    mutations = [m for row in rows for m in row['omission_mutations'] if m['expected_status'] == 'FAIL']
    rejected = sum(m['verification']['status'] == 'FAIL' for m in mutations)
    html = '<section><h2>Una spiegazione per ogni osservazione</h2>' + paragraph(
        'Ogni osservazione conservata mantiene la propria fonte, i dati estratti e una spiegazione dedicata. '
        'Quando una relazione comprende più studi, il modello aggiunge un confronto tra popolazioni, trattamenti, '
        'risultati e limiti documentati. Più passaggi dello stesso articolo restano osservazioni dello stesso studio.') + paragraph(
        f'Le dieci prove comprendono sei scenari sintetici dichiarati e quattro sottoinsiemi di dossier archiviati. '
        f'{passed} risposte su {len(rows)} superano i controlli. Eliminando una spiegazione o un confronto obbligatorio, '
        f'{rejected} alterazioni su {len(mutations)} vengono respinte. Il confronto tra passaggi dello stesso studio è facoltativo.') + paragraph(
        'La copertura controlla la presenza delle spiegazioni e la conservazione esatta dei dati. '
        'Citazioni e quantità vengono controllate anche rispetto alla singola osservazione. '
        'La qualità e la completezza semantica delle parafrasi richiedono ancora valutazione dedicata.') + paragraph(
        'Il percorso LIVE seleziona per impostazione predefinita fino a due documenti per associazione. '
        'Il limite è configurabile: la copertura riguarda le osservazioni conservate nel dossier. '
        'Le prove multistudio qui sotto utilizzano dati sintetici; i dossier BRAF disponibili contengono relazioni distinte.')
    names = {'concordant_results': 'Risultati concordanti', 'contrasting_results': 'Risultati contrastanti',
             'different_populations': 'Popolazioni diverse', 'combination_and_monotherapy': 'Combinazione e monoterapia',
             'two_passages_one_study': 'Due passaggi dello stesso studio',
             'excluded_second_observation': 'Una seconda osservazione esclusa',
             'BRAF_three_relations': 'BRAF: tre relazioni documentate, una pubblicazione per relazione'}
    # The archived transversal example is visible first. Synthetic results stay explicitly identified.
    ordered = sorted(rows, key=lambda row: (row['name'] != 'BRAF_three_relations', row['origin'] == 'SYNTHETIC_CONTRACT_FIXTURE'))
    for row in ordered:
        title = names.get(row['name'], row['name'].replace('BRAF_', 'BRAF · PMID '))
        synthetic = row['origin'] == 'SYNTHETIC_CONTRACT_FIXTURE'
        html += ('<section>' if row['name'] == 'BRAF_three_relations' else '<details><summary>' + escape(title) +
                 (' · caso sintetico' if synthetic else ' · fonte archiviata') + '</summary>')
        if row['name'] == 'BRAF_three_relations':
            html += '<h3>' + escape(title) + '</h3>'
        if synthetic:
            html += paragraph('<strong>Fixture sintetica:</strong> fonti, identificativi e risultati servono a provare il contratto di narrazione.')
        html += paragraph(escape(row['narrator_input']['case_overview']))
        html += paragraph('Esito dei controlli: <strong>' + escape(row['verification']['status']) + '</strong>.')
        narrative = row['call'].get('narrative') or {}
        generated = {entry['candidate_id']: entry for entry in narrative.get('candidate_narratives') or []}
        accepted = row['verification']['status'] == 'PASS'
        for candidate in row['narrator_input']['candidates']:
            entry = generated.get(candidate['candidate_id'], {})
            explanations = {item['observation_id']: item for item in entry.get('observation_narratives') or []}
            if accepted and entry.get('text'):
                html += paragraph(escape(entry['text']))
            for index, observation in enumerate(candidate.get('narration_observations') or [], 1):
                html += '<h3>Osservazione ' + str(index) + '</h3>'
                unit = (observation.get('source') or {}).get('source_unit_id')
                cards = [card for card in candidate.get('source_cards') or [] if card.get('source_unit_id') == unit]
                if cards:
                    html += source_card_html(cards[0])
                html += observation_facts_html(observation)
                if accepted:
                    explanation = explanations.get(observation['observation_id'], {})
                    html += '<h3>Spiegazione dell’osservazione</h3>' + paragraph(escape(explanation.get('text', '')))
                    if explanation.get('case_relevance'):
                        html += '<h3>Collegamento con il caso</h3>' + paragraph(escape(explanation['case_relevance']))
            if accepted and entry.get('study_comparison'):
                study_count = len({observation['study_id'] for observation in candidate.get('narration_observations') or []})
                heading = 'Confronto tra gli studi' if study_count > 1 else 'Confronto tra passaggi dello stesso studio'
                html += '<h3>' + heading + '</h3>' + paragraph(escape(entry['study_comparison']['text']))
        if accepted and narrative.get('limitations_summary'):
            html += paragraph(escape(narrative['limitations_summary']))
        if not accepted:
            html += '<details><summary>Risposta respinta e motivi</summary><pre>' + escape(
                json.dumps({'response': narrative, 'reasons': row['verification']['reason_codes']}, ensure_ascii=False, indent=2)) + '</pre></details>'
        html += '</section>' if row['name'] == 'BRAF_three_relations' else '</details>'
    html += paragraph('<a href="verifica/narratore-multistudio.json" download>Dieci prove: fonti, risposte e controlli delle omissioni · JSON</a>') + '</section>'
    (HERE / 'verifica/narratore-multistudio.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return html


def render_test_report(base: str, source: Path):
    """Expose measured behavior separately from the architectural explanation."""
    report = json.loads(source.read_text(encoding='utf-8'))
    records = report['cases']
    titles = ['Supporto completo', 'Relazione ambigua', 'Direzione non supportata',
              'Citazione assente', 'Due relazioni con esiti diversi', 'Supporto parziale',
              'Registro di studio', 'Sola provenienza nel grafo',
              'Fusione RET: osservazione esclusa e ricerca senza osservazione',
              'BRAF: osservazioni documentali conservate']
    passed = sum(row.get('verification', {}).get('status') == 'PASS' for row in records)
    mutations = [m for row in records if row.get('verification', {}).get('status') == 'PASS'
                 for m in row.get('mutations', [])]
    detected = sum(m['status'] == 'FAIL' for m in mutations)
    main = ('<main class="audit-main" id="main"><h1>Il dossier spiegato a partire dalle fonti</h1>' +
        paragraph('<a href="Audit_semantico_del_dossier.html">Leggi la valutazione semantica: rilievi e spiegazioni da rivedere</a>') +
        multistudy_narration_html() + '<details><summary>Precedenti prove sulle singole fonti</summary>' +
        documented_narration_html() + '</details><details><summary>Test storici del contratto: dieci scenari</summary>' + paragraph(
        f'Il modello ha prodotto una risposta strutturata per {len(records)} scenari. '
        f'{passed} spiegazioni superano i controlli implementati; {len(records) - passed} vengono respinte. '
        'Il prompt è in inglese e richiede testo in italiano.') + paragraph(
        'Otto scenari sono fixture sintetiche del contratto; due usano sottoinsiemi dichiarati '
        'di dossier di ricerca archiviati. Le relazioni e le osservazioni archiviate sono conservate; '
        'il recupero delle fonti e le decisioni sulle evidenze restano quelli già disponibili. '
        'Questa prova misura conformità alle regole del verificatore, distinta dall’accuratezza clinica '
        'e da una prova generale di equivalenza semantica.') + paragraph(
        '<a href="Prompt_di_sistema_per_il_relatore.html#narratore">Torna al prompt e al ruolo del narratore</a>') + table(
        ['Scenario', 'Tipo di dati', 'Controlli sulla prosa', 'Ripiego verificato'], [
            [title, 'Sintetico' if row['origin'] == 'SYNTHETIC_CONTRACT_FIXTURE' else 'Sottoinsieme archiviato',
             row.get('verification', {}).get('status', 'NON ESEGUITO'),
             row.get('fallback_verification', {}).get('status', 'NON ESEGUITO')]
            for title, row in zip(titles, records)]) + '<section><h2>Che cosa mostrano gli esiti</h2>' + paragraph(
        'Il caso di registro viene respinto da un controllo conservativo: il verificatore accetta '
        'formulazioni molto circoscritte per descrivere associazione ed efficacia. Alcune parafrasi '
        'descrittive del modello ricadono fuori da questo perimetro. Il rifiuto conserva il proprio '
        'esito e il testo deterministico viene verificato separatamente.') + paragraph(
        'Nel caso RET una voce priva di osservazioni e tentativi conservati viene descritta dal modello '
        'come ricerca che non ha reperito documenti. Il controllo aggiunto respinge questa inferenza: '
        'assenza di osservazioni nel dossier e fallimento del recupero documentale restano distinti.') + paragraph(
        f'Sulle {passed} risposte inizialmente conformi sono state applicate {len(mutations)} alterazioni: '
        f'{detected} sono respinte. Le alterazioni aggiungono un farmaco, una quantità o una fonte, '
        'introducono una raccomandazione, eliminano una voce oppure cambiano il legame con l’ingresso. '
        'Le alterazioni del testo già respinto sono conservate nei dati e tenute separate da questo conteggio.') +
        paragraph('Le regole verificano vincoli riconoscibili. Parafrasi nuove, inferenze implicite, '
                  'omissioni sottili e interpretazioni del bersaglio del grafo richiedono ancora una '
                  'valutazione semantica dedicata. Il superamento di queste prove ha questo perimetro.') + '</section>')
    for title, row in zip(titles, records):
        narrative = row.get('narrative')
        main += '<section><h2>' + escape(title) + '</h2>'
        case = row['narrator_input'].get('case') or {}
        main += paragraph(escape(' · '.join(str(case[key]) for key in ('disease', 'target_intervention') if case.get(key))))
        main += paragraph('Esito dei controlli: <strong>' + escape(row['verification']['status']) + '</strong>.')
        if narrative:
            main += '<details><summary>Leggi la risposta effettiva del modello</summary>'
            main += paragraph(escape(narrative['narrative_summary']))
            for entry in narrative['candidate_narratives']:
                main += paragraph(escape(entry['text']))
            main += paragraph(escape(narrative['limitations_summary']))
            main += paragraph(escape(narrative['closing_note'])) + '</details>'
        if row['verification']['reason_codes']:
            main += '<details><summary>Motivi tecnici del rifiuto</summary><pre>' + escape(
                '\n'.join(row['verification']['reason_codes'])) + '</pre></details>'
        main += '</section>'
    main += paragraph('<a href="verifica/narratore-dieci-casi.json" download>Ingressi, risposte, controlli e alterazioni · JSON</a>') + '</details></main>'
    page = re.sub(r'<main class="audit-main" id="main">.*?</main>', lambda _: main, base, flags=re.S)
    page = re.sub(r'<title>.*?</title>', '<title>Dossier: fonti, spiegazioni e prove</title>', page, count=1)
    (HERE / 'Prove_narratore_per_il_relatore.html').write_text(page, encoding='utf-8')
    (HERE / 'verifica/narratore-dieci-casi.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graphviz', default='C:/Program Files/Graphviz/bin/dot.exe')
    build(parser.parse_args().graphviz)

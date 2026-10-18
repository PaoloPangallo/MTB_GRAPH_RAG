"""Present repaired narration and the unchanged semantic audit side by side."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from evaluation.run_narrator_semantic_audit import REPO, judge_errors, prepare_cases
from evaluation.build_narrator_semantic_report import build_audit, render_html, WEB, LABELS, NAMES, table, p

RESPONSES = REPO / 'evaluation/multistudy_narrator_v51_verified/results.json'
JUDGEMENTS = REPO / 'evaluation/narrator_semantic_audit_repaired/results.json'


def build_repair_report():
    baseline = build_audit()
    before = {row['name']: row for row in baseline['cases']}
    original = json.loads((REPO / 'evaluation/multistudy_narrator_verified/results.json').read_text(encoding='utf-8'))
    original = {row['name']: row for row in original['cases']}
    repaired = json.loads(RESPONSES.read_text(encoding='utf-8'))
    graded = json.loads(JUDGEMENTS.read_text(encoding='utf-8'))
    prepared = {row['name']: row for row in prepare_cases(RESPONSES)}
    grades = {row['name']: row for row in graded['cases']}
    if set(grades) != set(before) or set(prepared) != set(before):
        raise ValueError('Repair audit case coverage mismatch')
    rows = []
    for row in repaired['cases']:
        name = row['name']; grade = grades[name]; payload = prepared[name]['payload']
        if grade['payload'] != payload:
            raise ValueError('Judge reviewed a different repaired response')
        judgement = grade['judge_call'].get('judgement')
        errors = judge_errors(judgement, payload) if judgement else ['JUDGEMENT_UNAVAILABLE']
        old = original[name]['call']['narrative']; current = row['call']['narrative']
        unchanged = all(old.get(key) == current.get(key) for key in ('canonical_sources', 'canonical_observations'))
        rows.append({'name': name, 'origin': row['origin'],
            'before_verdict': before[name]['codex_review']['verdict'],
            'mechanical_verification': row['verification'],
            'semantic_verdict': judgement['verdict'] if not errors else 'UNASSESSABLE',
            'semantic_judgement': judgement, 'evidence_errors': errors,
            'sources_and_observations_unchanged': unchanged, 'payload': payload})
    return {'scope': 'REGRESSION_ON_THE_TEN_PREVIOUSLY_AUDITED_CASES',
        'same_grader_prompt': graded['grader_prompt_version'],
        'same_model_as_narrator': graded['same_model_as_narrator'],
        'production_semantic_model_gate_added': False,
        'summary': {'cases': len(rows),
            'mechanical_pass': sum(row['mechanical_verification']['status'] == 'PASS' for row in rows),
            'semantic_acceptable': sum(row['semantic_verdict'] == 'ACCEPTABLE' for row in rows),
            'sources_and_observations_unchanged': sum(row['sources_and_observations_unchanged'] for row in rows)},
        'cases': rows, 'baseline': baseline,
        'provenance': [{'file': path.relative_to(REPO).as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()}
                       for path in (RESPONSES, JUDGEMENTS, Path(__file__).resolve())]}


def render_repair_html(report):
    summary = report['summary']
    main = '<main class="audit-main" id="main"><h1>Dossier: correzioni e verifica semantica</h1>'
    main += p(f"Le risposte corrette superano i controlli deterministici in {summary['mechanical_pass']} casi su {summary['cases']} "
              f"e risultano accettabili alla nuova lettura semantica in {summary['semantic_acceptable']} casi su {summary['cases']}. "
              'Il confronto ora esplicita popolazione, trattamento e rapporto con la domanda del caso per ogni osservazione.')
    main += p('Le criticità precedenti sono state corrette nel prompt e nel contratto della risposta. '
              'Le nuove spiegazioni sono state generate dal provider: i testi originali delle prove precedenti restano consultabili.')
    main += '<p><a href="Prove_narratore_per_il_relatore.html">Leggi le nuove risposte con le fonti</a> · '
    main += '<a href="Prompt_di_sistema_per_il_relatore.html#narratore">Prompt e ruolo del narratore</a></p>'
    main += '<section><h2>Che cosa è stato corretto</h2>' + table(['Problema emerso', 'Comportamento attuale'], [
        ['Popolazione della fonte e del caso', 'Il raccordo esplicita stadio III adiuvante e caso metastatico quando presenti.'],
        ['Interventi diversi', 'Monoterapia, vemurafenib e combinazione dabrafenib–trametinib restano distinti rispetto alla domanda.'],
        ['Significato del controllo sulla malattia', 'La spiegazione parla della corrispondenza con il caso; mantiene distinta la diagnosi nella fonte.'],
        ['Varianti alternative', 'V600E e V600K vengono descritte come alternative tra pazienti.'],
        ['Dossier con più relazioni', 'Ogni osservazione conserva il proprio raccordo con il caso e il limite clinico comune compare una volta.'],
        ['Controlli sul nuovo testo', 'Anche il raccordo con il caso partecipa ai controlli su fonti, citazioni e quantità.']]) + '</section>'
    main += '<section><h2>Prima e dopo</h2>' + table(['Caso', 'Audit precedente', 'Nuova lettura semantica'], [
        [NAMES.get(row['name'], row['name'].replace('BRAF_', 'BRAF · PMID ')), LABELS[row['before_verdict']], LABELS[row['semantic_verdict']]]
        for row in report['cases']])
    main += p(f"Fonti e osservazioni originali risultano identiche in {summary['sources_and_observations_unchanged']} "
              f"casi su {summary['cases']}. Il prompt del valutatore è quello già calibrato; le nuove spiegazioni "
              'sono state esaminate anche confrontando direttamente i passaggi corretti con gli ingressi.') + '</section>'
    main += '<section><h2>Esempi del raccordo con il caso</h2>'
    for name in ('BRAF_28891408', 'BRAF_22663011', 'BRAF_24508103', 'BRAF_three_relations'):
        row = next(row for row in report['cases'] if row['name'] == name)
        main += '<details><summary>' + escape(NAMES.get(name, name.replace('BRAF_', 'BRAF · PMID '))) + '</summary>'
        for entry in row['payload']['narrative']['candidate_narratives']:
            for item in entry.get('observation_narratives') or []:
                main += p(item['case_relevance'])
        main += p(row['payload']['narrative']['limitations_summary']) + '</details>'
    main += '</section><section><h2>Perimetro della verifica</h2>'
    main += p('Le prove comprendono sei scenari sintetici e quattro sottoinsiemi archiviati, che riutilizzano tre pubblicazioni. '
              f"L’esito {summary['semantic_acceptable']}/{summary['cases']} riguarda questi casi già conosciuti: misura la correzione delle regressioni osservate. "
              'Generalizzazione, altre famiglie di relazioni e valutazione clinica richiedono prove ulteriori.')
    model_description = ('Il valutatore automatico usa lo stesso modello del narratore con un ruolo diverso. '
                         if report['same_model_as_narrator'] else 'Il valutatore usa un modello diverso da quello del narratore. ')
    main += p(model_description +
              'La revisione assistita resta distinta da una validazione umana. Il verificatore della produzione '
              'controlla la presenza del raccordo e vincoli specifici; l’audit semantico continua come valutazione separata.')
    main += '<p><a href="verifica/narratore-audit-correzioni.json" download>Confronto, nuove risposte e giudizi · JSON</a></p></section>'
    historical = render_html(report['baseline'])
    content = re.search(r'<main class="audit-main" id="main">(.*?)</main>', historical, flags=re.S).group(1)
    main += '<details><summary>Audit precedente: rilievi, prove e limiti del valutatore</summary>' + content + '</details></main>'
    page = re.sub(r'<main class="audit-main" id="main">.*?</main>', lambda _: main, historical, flags=re.S)
    return re.sub(r'<title>.*?</title>', '<title>Dossier: correzioni e verifica semantica</title>', page, count=1)


def main():
    report = build_repair_report()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (REPO / 'evaluation/narrator_semantic_audit_repaired/repair-report.json').write_text(text, encoding='utf-8')
    (WEB / 'verifica/narratore-audit-correzioni.json').write_text(text, encoding='utf-8')
    (WEB / 'Audit_semantico_del_dossier.html').write_text(render_repair_html(report), encoding='utf-8')
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()

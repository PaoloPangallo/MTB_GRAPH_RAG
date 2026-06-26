import json, re, sys
sys.stdout.reconfigure(encoding='utf-8')

g = json.load(open(r'mtb-graphrag\backend\evaluation\results\ablation_second_llm_graphrag_results.json','r',encoding='utf-8'))

for r in g:
    report = r['report']
    # Cerca numeri da 7 a 9 cifre che potrebbero essere PMID
    digits = re.findall(r'\b\d{7,9}\b', report)
    if digits:
        printed_case = False
        for d in digits:
            # Vediamo se la parola PMID è presente vicino al numero (entro 15 caratteri a sinistra)
            match_pos = report.find(d)
            if match_pos != -1:
                start = max(0, match_pos - 30)
                end = min(len(report), match_pos + 30)
                context = report[start:end].replace('\n', ' ')
                # Se non c'è "PMID" (case insensitive) nei 25 caratteri precedenti
                left_context = report[max(0, match_pos - 25):match_pos].lower()
                if "pmid" not in left_context:
                    if not printed_case:
                        print(f"\nCASO: {r['case_id']}")
                        printed_case = True
                    print(f"  Trovato numero sospetto {d} senza 'PMID' vicino: ... {context} ...")


import re

_BLOCK_RE = re.compile(r'\bPMID[:\s]*(\d{5,9}(?:(?:[\s,;]+|[\s,;]+(?:and|or|e|o)[\s,;]+)\d{5,9})*)\b', re.IGNORECASE)
_PMID_DIGITS_RE = re.compile(r'\b\d{5,9}\b')

def filtra_pmid_non_verificati(report_text: str, verified_pmids: set[int]) -> tuple[str, list[int]]:
    rimossi = []

    def sostituisci_blocco(match):
        block_text = match.group(0)
        nums = [int(n) for n in _PMID_DIGITS_RE.findall(block_text)]
        
        nuovo_block = block_text
        for n in nums:
            if n not in verified_pmids:
                rimossi.append(n)
                # Sostituiamo il pmid non verificato nel blocco
                nuovo_block = re.sub(rf'\b{n}\b', "[PMID non verificato nel KG]", nuovo_block)
        return nuovo_block

    testo_filtrato = _BLOCK_RE.sub(sostituisci_blocco, report_text)
    return testo_filtrato, rimossi

# Test cases
verified = {26047531, 30124952, 26851330, 14645423, 23470965} # alcuni verificati, altri no

reports = [
    "RATIFY [PMID: 26047531] (verificato) e [PMID: 99999999] (non verificato)",
    "Bypass MET: [PMID: 26851330, 33576433] (uno verificato, uno no)",
    "Molti: [PMID: 14645423; 18955451; 23177515] (due non verificati)",
    "Congiunzione: [PMID: 25668228, 21430269 e 23470965] (uno verificato in fondo)",
]

for r in reports:
    filtrato, rm = filtra_pmid_non_verificati(r, verified)
    print(f"Original: {r}")
    print(f"Filtered: {filtrato}")
    print(f"Removed:  {rm}\n")

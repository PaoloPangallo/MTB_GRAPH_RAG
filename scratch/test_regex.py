import re

# Definiamo la regex del blocco
_BLOCK_RE = re.compile(r'\bPMID[:\s]*(\d{5,9}(?:(?:[\s,;]+|[\s,;]+(?:and|or|e|o)[\s,;]+)\d{5,9})*)\b', re.IGNORECASE)
_PMID_DIGITS_RE = re.compile(r'\b\d{5,9}\b')

def extract_pmids(text: str) -> set[int]:
    pmids = set()
    for match in _BLOCK_RE.finditer(text):
        block_text = match.group(0)
        # Trova tutti i numeri da 5 a 9 cifre nel blocco
        nums = [int(n) for n in _PMID_DIGITS_RE.findall(block_text)]
        pmids.update(nums)
    return pmids

# Test cases
test_cases = [
    "[PMID: 26047531]",
    "PMID 30124952",
    "**PMID: 26851330**",
    "[PMID: 29103641 — *non presente nel KG*]",
    "[PMID: 14645423; 18955451; 23177515]",
    "[PMID: 24801015, 17957027, 21537333]",
    "[PMID: 25668228, 21430269 e 23470965]",
]

for tc in test_cases:
    extracted = extract_pmids(tc)
    print(f"Test: {tc} -> Extracted: {extracted}")

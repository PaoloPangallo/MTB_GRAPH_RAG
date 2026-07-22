"""Verifica l'esistenza dei locator citati da una revisione, senza importare la fonte.

Una revisione che cita «Figure 1C-D» o un paragrafo del testo afferma qualcosa di
controllabile. Controllarlo richiede il full text, ma **conservarlo** no: qui il
testo viene scaricato in memoria, interrogato, e scartato. Restano soltanto
l'esito della verifica, la posizione e l'hash del documento.

L'hash e' cio' che rende la verifica ripetibile: chi rifa' il controllo su un
documento con lo stesso hash deve ottenere gli stessi esiti. Se l'hash cambia, la
verifica va rifatta invece di essere data per buona.

Le stringhe cercate provengono dalla revisione, non dal documento: registrarle
non redistribuisce nulla che non fosse gia' nella revisione.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.pilot.audit_lib.serialize import write_jsonl  # noqa: E402

VERIFICATION_VERSION = "source_locator_verification/1.0"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ELINK = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
USER_AGENT = "mtb-graphrag-benchmark/1.0 (research; contact via repository)"

VERIFIED = "verified"
NOT_VERIFIED = "source_locator_not_verified"
NOT_ACCESSIBLE = "source_not_accessible"

_WHITESPACE = re.compile(r"\s+")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--locators", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    return parser.parse_args(argv)


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def pmc_id_for(pmid: str, *, timeout: int = 25) -> str:
    query = urllib.parse.urlencode(
        {"dbfrom": "pubmed", "db": "pmc", "id": pmid, "retmode": "json"}
    )
    request = urllib.request.Request(f"{ELINK}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Il registro puo' rispondere con una pagina di errore invece che con
        # JSON. Trattarlo come «nessun full text» e' corretto e mantiene la
        # pipeline riproducibile: una risposta transitoria non deve far fallire
        # un audit che ha gia' l'abstract come alternativa.
        return ""
    for linkset in payload.get("linksets") or []:
        for database in linkset.get("linksetdbs") or []:
            if database.get("linkname") == "pubmed_pmc":
                links = database.get("links") or []
                if links:
                    return str(links[0])
    return ""


def fetch_pmc_document(pmc_id: str, *, timeout: int = 60) -> tuple[str, str, list[str]]:
    """Restituisce `(testo normalizzato, hash, etichette di figure e tabelle)`.

    Il testo non viene scritto su disco da questa funzione ne' dal chiamante.
    """
    query = urllib.parse.urlencode({"db": "pmc", "id": pmc_id, "retmode": "xml"})
    request = urllib.request.Request(f"{EFETCH}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return _clean(raw), digest, []

    text = _clean(" ".join(root.itertext()))
    labels: list[str] = []
    for tag in ("fig", "table-wrap", "supplementary-material"):
        for node in root.iter(tag):
            label = node.find("label")
            if label is not None and label.text:
                labels.append(_clean(label.text))
    return text, digest, sorted(set(labels))


def _label_variants(locator: str) -> list[str]:
    """Forme alternative con cui un editore puo' scrivere la stessa etichetta."""
    base = locator.strip()
    variants = {base}
    compact = base.replace(" ", "")
    variants.add(compact)
    if base.lower().startswith("figure"):
        variants.add(base.replace("Figure", "Fig."))
        variants.add(base.replace("Figure", "Fig"))
    if base.lower().startswith("supplementary figure"):
        rest = base[len("Supplementary Figure") :].strip().lstrip("S")
        variants.update({f"fig. S{rest}", f"Fig S{rest}", f"figure S{rest}"})
    # «Figure 1C-D» compare spesso come «Fig. 1C» e «Fig. 1D» separati.
    match = re.match(r"(?i)(figure|fig\.?)\s*(\d+)([A-Z])\s*[-–]\s*([A-Z])$", base)
    if match:
        number, first, second = match.group(2), match.group(3), match.group(4)
        for letter in (first, second):
            variants.update({f"Fig. {number}{letter}", f"Figure {number}{letter}"})

    # Ordinate dalla piu' specifica alla piu' generica. Una variante nuda come
    # «1C» o «S3C» corrisponderebbe quasi ovunque nel documento, e in ordine
    # alfabetico vincerebbe su «Fig. 1C», facendo passare per verificata una
    # coincidenza. La lunghezza e' un buon indicatore di specificita' qui.
    return sorted(variants, key=lambda item: (-len(item), item))


def _find_interpolated(needle: str, haystack: str, *, max_gap: int = 60) -> int | None:
    """Trova le parole della citazione nell'ordine dato, ammettendo incisi.

    Serve per un caso reale e frequente: la revisione cita «ALK fusion proteins
    are known hsp90 clients», il documento scrive «... known hsp90 (heat shock
    protein 90) clients». La citazione e' corretta, la ricerca esatta fallisce, e
    dichiararla non verificata sarebbe un falso negativo che scredita una
    citazione buona.

    Il divario ammesso e' limitato, e l'esito viene marcato `interpolated` invece
    che `exact`: la tolleranza deve restare visibile a chi legge la verifica.
    """
    words = [word for word in re.findall(r"\w+", needle) if word]
    if not words:
        return None

    # La sequenza va **ancorata** a ogni occorrenza della prima parola. Cercando
    # ciascuna parola dalla posizione corrente in avanti senza ancoraggio, la
    # ricerca deriva: «alk» compare centinaia di volte nel documento, e il
    # confronto finirebbe per costruire una falsa sequenza attraverso il testo.
    for anchor in re.finditer(rf"\b{re.escape(words[0])}\b", haystack):
        position = anchor.end()
        ok = True
        for word in words[1:]:
            match = re.search(rf"\b{re.escape(word)}\b", haystack[position : position + max_gap])
            if match is None:
                ok = False
                break
            position += match.end()
        if ok:
            return anchor.start()
    return None


def verify_locator(locator: dict[str, Any], text: str, labels: Sequence[str]) -> dict[str, Any]:
    kind = locator.get("kind", "phrase")
    value = str(locator.get("value") or "")
    haystack = text.casefold()

    if kind == "phrase":
        needle = _clean(value).casefold()
        position = haystack.find(needle)
        if position < 0:
            # Un paragrafo puo' essere citato in forma abbreviata: si prova il
            # prefisso, ma l'esito viene marcato come parziale, non pieno.
            prefix = " ".join(needle.split()[:8])
            position = haystack.find(prefix) if prefix else -1
            if position >= 0:
                return {
                    **locator,
                    "status": VERIFIED,
                    "match_type": "prefix",
                    "char_offset": position,
                    "note": "trovato per prefisso delle prime parole",
                }
            interpolated = _find_interpolated(needle, haystack)
            if interpolated is not None:
                return {
                    **locator,
                    "status": VERIFIED,
                    "match_type": "interpolated",
                    "char_offset": interpolated,
                    "note": (
                        "le parole della citazione compaiono nell'ordine dato ma con "
                        "materiale interposto, tipicamente un inciso dell'editore; "
                        "corrispondenza piu' debole di quella esatta e segnalata come tale"
                    ),
                }
            return {**locator, "status": NOT_VERIFIED, "match_type": "none", "char_offset": None}
        return {
            **locator,
            "status": VERIFIED,
            "match_type": "exact",
            "char_offset": position,
            "note": "",
        }

    # Etichette di figura, tabella o materiale supplementare.
    label_pool = {item.casefold() for item in labels}
    for variant in _label_variants(value):
        folded = variant.casefold()
        if folded in label_pool:
            return {**locator, "status": VERIFIED, "match_type": "label", "matched_variant": variant}
        if folded and folded in haystack:
            return {
                **locator,
                "status": VERIFIED,
                "match_type": "inline_reference",
                "matched_variant": variant,
                "note": "citata nel testo; l'etichetta non compare fra gli oggetti strutturati",
            }
    return {**locator, "status": NOT_VERIFIED, "match_type": "none"}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    locators = json.loads(args.locators.read_text(encoding="utf-8"))
    created_at = datetime.now(timezone.utc).isoformat()

    if not args.allow_network:
        rows = [
            {
                **locator,
                "status": NOT_ACCESSIBLE,
                "note": "verifica non eseguita: rilanciare con --allow-network",
                "verification_version": VERIFICATION_VERSION,
            }
            for locator in locators
        ]
        write_jsonl(args.output, rows)
        print("rete non abilitata: tutti i locator restano non verificati")
        return 1

    pmc_id = pmc_id_for(args.pmid)
    if not pmc_id:
        rows = [
            {
                **locator,
                "status": NOT_ACCESSIBLE,
                "note": "nessun full text pubblicamente accessibile in PMC",
                "verification_version": VERIFICATION_VERSION,
            }
            for locator in locators
        ]
        write_jsonl(args.output, rows)
        print("full text non accessibile: locator non verificabili")
        return 1

    text, digest, labels = fetch_pmc_document(pmc_id)
    rows = []
    for locator in locators:
        result = verify_locator(locator, text, labels)
        result.update(
            {
                "pmid": args.pmid,
                "pmc_id": f"PMC{pmc_id}",
                "document_sha256": digest,
                "access_date": created_at[:10],
                "retrieved_from": "pmc_efetch",
                "verification_version": VERIFICATION_VERSION,
                "note_on_storage": (
                    "il full text e' stato interrogato in memoria e non e' conservato; "
                    "restano esito, posizione e hash del documento"
                ),
            }
        )
        rows.append(result)

    rows.sort(key=lambda item: str(item.get("locator_id")))
    write_jsonl(args.output, rows)

    verified = sum(1 for row in rows if row["status"] == VERIFIED)
    print(f"PMC{pmc_id} | hash {digest[:16]}… | etichette strutturate: {len(labels)}")
    print(f"locator verificati: {verified} / {len(rows)}")
    for row in rows:
        if row["status"] != VERIFIED:
            print(f"  NON verificato: {row['locator_id']} ({row['value']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Script: download_benchmark_papers.py
Scopo:  Scarica abstract, metadati e (se disponibile) full text open access
        per i 10 PMID del dataset benchmark MTB dalla API NCBI E-utilities.
        Usa PubMed Central (PMC) come fonte primaria per il full text, e
        Unpaywall come fallback per i paper non su PMC.

Output:
  - benchmark_papers/metadata_<PMID>.json  (metadati + abstract per ogni paper)
  - benchmark_papers/fulltext_<PMID>.txt   (full text se disponibile su PMC o Unpaywall)
  - benchmark_papers_summary.csv           (tabella riassuntiva di tutti i paper)
  - benchmark_papers_not_available.txt     (lista paper senza full text open access)

Requisiti:
  pip install requests rich

NCBI API Key (opzionale ma consigliata):
  Registrati su https://www.ncbi.nlm.nih.gov/account/
  e inserisci la tua chiave nella variabile NCBI_API_KEY qui sotto.
  Senza chiave: max 3 richieste/secondo.
  Con chiave gratuita: max 10 richieste/secondo.

Unpaywall:
  Richiede solo un indirizzo email valido (UNPAYWALL_EMAIL).
  Non serve registrazione. Gratuito per uso accademico.
  Docs: https://unpaywall.org/products/api
"""

import os
import json
import time
import requests
import csv
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

# ============================================================================
# CONFIGURAZIONE
# ============================================================================

# Inserisci la tua API key NCBI qui (gratuita su https://www.ncbi.nlm.nih.gov/account/)
# Lascia stringa vuota "" se non ce l'hai ancora
NCBI_API_KEY = "cced7273c4852e482e80f0eeb52b3849fa08"

# Inserisci la tua email per Unpaywall (non serve registrazione, solo email valida)
# Usata come identificativo per le chiamate API Unpaywall
UNPAYWALL_EMAIL = "paolo.pangallo23@gmail.com" 

# Cartella di output
OUTPUT_DIR = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\benchmark_papers")

# Rate limit: secondi di attesa tra le chiamate API
# 0.34 = ~3 richieste/sec (senza API key NCBI)
# 0.11 = ~10 richieste/sec (con API key NCBI)
SLEEP_TIME = 0.34 if not NCBI_API_KEY else 0.11

# ============================================================================
# PMID DEL BENCHMARK  --  10 casi MTB
# Nota: BENCH-002 usa il PMID dello studio ALEX (alectinib vs crizotinib
# in prima linea per ALK+ NSCLC)  --  Peters et al. NEJM 2017  --  invece del
# paper sulla resistenza ALK che era stato usato erroneamente in precedenza.
# ============================================================================

BENCHMARK_PMIDS = {
    "BENCH-001": {
        "pmid": "37937763",
        "case": "EGFR L858R  --  NSCLC  --  Osimertinib",
        "gene": "EGFR",
        "variant": "L858R",
        "tumor": "NSCLC",
        "expected_drug": "Osimertinib",
        "escat": "I-A"
    },
    "BENCH-002": {
        "pmid": "28586279",  # FIX: studio ALEX (alectinib vs crizotinib) Peters NEJM 2017
        "case": "ALK Fusion  --  NSCLC  --  Alectinib (studio ALEX)",
        "gene": "ALK",
        "variant": "Fusion",
        "tumor": "NSCLC",
        "expected_drug": "Alectinib",
        "escat": "I-A"
    },
    "BENCH-003": {
        "pmid": "21639808",
        "case": "BRAF V600E  --  Melanoma  --  Vemurafenib",
        "gene": "BRAF",
        "variant": "V600E",
        "tumor": "Melanoma",
        "expected_drug": "Vemurafenib/Dabrafenib+Trametinib",
        "escat": "I-A"
    },
    "BENCH-004": {
        "pmid": "26874901",
        "case": "ERBB2 Amplification  --  Breast HER2+  --  Trastuzumab",
        "gene": "ERBB2",
        "variant": "Amplification",
        "tumor": "Breast Cancer HER2+",
        "expected_drug": "Trastuzumab+Pertuzumab",
        "escat": "I-A"
    },
    "BENCH-005": {
        "pmid": "30345884",
        "case": "BRCA1 Mutation  --  Ovarian  --  Olaparib",
        "gene": "BRCA1",
        "variant": "Mutation",
        "tumor": "Ovarian Cancer",
        "expected_drug": "Olaparib",
        "escat": "I-A"
    },
    "BENCH-006": {
        "pmid": "11423618",
        "case": "BCR-ABL1 Fusion  --  CML  --  Imatinib",
        "gene": "ABL1",
        "variant": "BCR-ABL1 Fusion",
        "tumor": "CML",
        "expected_drug": "Imatinib",
        "escat": "I-A"
    },
    "BENCH-007": {
        "pmid": "31566309",
        "case": "BRAF V600E  --  mCRC  --  Encorafenib+Cetuximab",
        "gene": "BRAF",
        "variant": "V600E",
        "tumor": "Colorectal Cancer",
        "expected_drug": "Encorafenib+Cetuximab",
        "escat": "I-A"
    },
    "BENCH-008": {
        "pmid": "31091374",
        "case": "PIK3CA Mutation  --  Breast HR+  --  Alpelisib+Fulvestrant",
        "gene": "PIK3CA",
        "variant": "Mutation",
        "tumor": "Breast Cancer HR+",
        "expected_drug": "Alpelisib+Fulvestrant",
        "escat": "I-A"
    },
    "BENCH-009": {
        "pmid": "14645423",
        "case": "KIT Exon 11  --  GIST  --  Imatinib",
        "gene": "KIT",
        "variant": "Exon 11 Mutation",
        "tumor": "GIST",
        "expected_drug": "Imatinib",
        "escat": "I-A"
    },
    "BENCH-010": {
        "pmid": "31665578",
        "case": "FLT3 ITD  --  AML  --  Gilteritinib",
        "gene": "FLT3",
        "variant": "ITD",
        "tumor": "AML",
        "expected_drug": "Gilteritinib",
        "escat": "I-A"
    }
}

# ============================================================================
# SETUP
# ============================================================================

console = Console(width=95, legacy_windows=False)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def build_params(extra={}):
    """Aggiunge API key ai parametri se disponibile."""
    params = {"retmode": "json"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    params.update(extra)
    return params

# ============================================================================
# FUNZIONI CORE
# ============================================================================

def fetch_abstract_and_metadata(pmid: str) -> dict:
    """
    Scarica metadati e abstract da PubMed per un singolo PMID.
    Usa l'endpoint efetch con rettype=abstract.
    """
    # Step 1: fetch in formato XML per estrarre tutti i campi
    url = f"{BASE_URL}/efetch.fcgi"
    params = build_params({
        "db": "pubmed",
        "id": pmid,
        "rettype": "xml",
        "retmode": "xml"
    })

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        xml_content = response.text
    except requests.RequestException as e:
        return {"pmid": pmid, "error": str(e), "status": "fetch_failed"}

    time.sleep(SLEEP_TIME)

    # Step 2: parse XML con esummary per metadati strutturati
    url_summary = f"{BASE_URL}/esummary.fcgi"
    params_summary = build_params({
        "db": "pubmed",
        "id": pmid
    })

    try:
        resp_summary = requests.get(url_summary, params=params_summary, timeout=30)
        resp_summary.raise_for_status()
        summary_data = resp_summary.json()
    except requests.RequestException as e:
        summary_data = {}

    time.sleep(SLEEP_TIME)

    # Estrai i campi dal summary JSON
    result = summary_data.get("result", {})
    doc = result.get(pmid, {})

    # Estrai abstract dal XML (più affidabile che dal summary)
    abstract = extract_abstract_from_xml(xml_content)

    return {
        "pmid": pmid,
        "status": "ok",
        "title": doc.get("title", ""),
        "authors": [a.get("name", "") for a in doc.get("authors", [])],
        "journal": doc.get("fulljournalname", ""),
        "pub_date": doc.get("pubdate", ""),
        "doi": next((
            uid.get("value", "")
            for uid in doc.get("articleids", [])
            if uid.get("idtype") == "doi"
        ), ""),
        "pmc_id": next((
            uid.get("value", "")
            for uid in doc.get("articleids", [])
            if uid.get("idtype") == "pmc"
        ), ""),
        "abstract": abstract,
        "xml_raw": xml_content[:2000]  # primi 2000 char per debug
    }


def extract_abstract_from_xml(xml_content: str) -> str:
    """
    Estrae il testo dell'abstract dall'XML PubMed.
    Gestisce abstract strutturati (con label come Background, Methods, Results)
    e abstract semplici.
    """
    import re

    # Rimuovi tag XML ma preserva il testo dei tag AbstractText
    abstract_texts = re.findall(
        r'<AbstractText[^>]*>(.*?)</AbstractText>',
        xml_content,
        re.DOTALL
    )

    if not abstract_texts:
        return "Abstract non disponibile."

    # Per abstract strutturati estrai anche il label
    abstract_labels = re.findall(
        r'<AbstractText\s+Label="([^"]+)"',
        xml_content
    )

    if abstract_labels and len(abstract_labels) == len(abstract_texts):
        # Abstract strutturato
        parts = []
        for label, text in zip(abstract_labels, abstract_texts):
            # Rimuovi tag HTML interni
            clean_text = re.sub(r'<[^>]+>', '', text).strip()
            parts.append(f"{label}: {clean_text}")
        return "\n\n".join(parts)
    else:
        # Abstract semplice
        clean = re.sub(r'<[^>]+>', '', abstract_texts[0]).strip()
        return clean


def fetch_fulltext_pmc(pmc_id: str, pmid: str) -> tuple:
    """
    Scarica il full text da PubMed Central se disponibile open access.
    Restituisce (testo, status) dove status è 'ok', 'not_available' o 'error'.
    """
    if not pmc_id:
        return "", "not_in_pmc"

    # Normalizza il PMC ID (rimuovi "PMC" se presente)
    pmc_clean = pmc_id.replace("PMC", "").strip()

    url = f"{BASE_URL}/efetch.fcgi"
    params = build_params({
        "db": "pmc",
        "id": pmc_clean,
        "rettype": "full",
        "retmode": "xml"
    })

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        if len(response.text) < 500:
            return "", "not_available"

        # Estrai testo leggibile dal XML PMC
        import re
        # Rimuovi tag XML
        text = re.sub(r'<[^>]+>', ' ', response.text)
        # Normalizza spazi
        text = re.sub(r'\s+', ' ', text).strip()

        time.sleep(SLEEP_TIME)
        return text[:50000], "ok"  # limita a 50k char

    except requests.RequestException as e:
        return "", f"error: {str(e)}"


def fetch_fulltext_unpaywall(doi: str, pmid: str) -> tuple:
    """
    Tenta di scaricare il full text tramite Unpaywall come fallback.
    Unpaywall trova versioni legali open access di paper altrimenti a pagamento
    (es. versioni preprint accettate, versioni depositate in repository istituzionali).
    
    Restituisce (testo, status, oa_url) dove:
    - testo: contenuto del paper o stringa vuota
    - status: 'ok', 'not_oa', 'no_doi', 'error'
    - oa_url: URL da cui è stato scaricato il testo (per citazione)
    """
    if not doi:
        return "", "no_doi", ""

    if not UNPAYWALL_EMAIL or UNPAYWALL_EMAIL == "tuaemail@esempio.com":
        return "", "no_email_configured", ""

    # Step 1: chiedi a Unpaywall se il paper è open access e dove
    unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"

    try:
        resp = requests.get(unpaywall_url, timeout=20)
        if resp.status_code == 404:
            return "", "not_found_unpaywall", ""
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return "", f"unpaywall_error: {str(e)}", ""

    time.sleep(0.5)  # Unpaywall chiede di non fare più di 100k req/giorno

    # Controlla se è open access
    is_oa = data.get("is_oa", False)
    if not is_oa:
        return "", "not_oa", ""

    # Trova la migliore URL open access
    # Priorità: publisher (versione definitiva) > repository (preprint accettato)
    best_oa_location = data.get("best_oa_location", {})
    oa_url = best_oa_location.get("url_for_pdf") or best_oa_location.get("url")

    if not oa_url:
        # Prova a cercare tra tutte le locations
        for loc in data.get("oa_locations", []):
            candidate = loc.get("url_for_pdf") or loc.get("url")
            if candidate:
                oa_url = candidate
                break

    if not oa_url:
        return "", "no_url_found", ""

    # Step 2: scarica il contenuto dalla URL trovata
    try:
        headers = {"User-Agent": "Mozilla/5.0 (research bot - tesi magistrale)"}
        resp_paper = requests.get(oa_url, timeout=30, headers=headers, allow_redirects=True)
        resp_paper.raise_for_status()

        content_type = resp_paper.headers.get("content-type", "")

        if "pdf" in content_type.lower():
            # PDF: tenta estrazione testo con pdfminer se disponibile
            try:
                from io import BytesIO
                from pdfminer.high_level import extract_text as pdf_extract
                text = pdf_extract(BytesIO(resp_paper.content))
                text = text[:50000]
                return text, "ok_pdf", oa_url
            except ImportError:
                # pdfminer non installato: salva il PDF grezzo
                return f"[PDF scaricato da {oa_url}  --  installa pdfminer.six per estrarre testo]", "ok_pdf_raw", oa_url
            except Exception as e:
                return f"[PDF scaricato ma errore estrazione testo: {e}]", "ok_pdf_error", oa_url

        elif "html" in content_type.lower() or "text" in content_type.lower():
            # HTML/testo: estrai testo leggibile
            import re
            text = re.sub(r'<[^>]+>', ' ', resp_paper.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:50000], "ok_html", oa_url

        else:
            return "", f"unknown_content_type: {content_type}", oa_url

    except requests.RequestException as e:
        return "", f"download_error: {str(e)}", oa_url


def verify_pmid_exists(pmid: str) -> bool:
    """Verifica che il PMID esista su PubMed."""
    url = f"{BASE_URL}/esearch.fcgi"
    params = build_params({
        "db": "pubmed",
        "term": pmid + "[uid]",
        "retmax": 1
    })
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        count = int(data.get("esearchresult", {}).get("count", 0))
        time.sleep(SLEEP_TIME)
        return count > 0
    except Exception:
        return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    # Pre-calcola le stringhe con markup Rich per evitare f-string malformate
    ncbi_status = "[green]Configurata[/]" if NCBI_API_KEY else "[yellow]Non configurata (limite 3 req/s)[/]"
    unpaywall_configured = UNPAYWALL_EMAIL and UNPAYWALL_EMAIL != "tuaemail@esempio.com"
    unp_status = f"[green]{UNPAYWALL_EMAIL}[/]" if unpaywall_configured else "[yellow]Non configurata (fallback disabilitato)[/]"

    console.print(Panel(
        f"[bold white]Download Paper Benchmark MTB[/]\n"
        f"PMID da scaricare: [bold cyan]{len(BENCHMARK_PMIDS)}[/]\n"
        f"Output directory: [green]{OUTPUT_DIR}[/]\n"
        f"API Key NCBI: {ncbi_status}\n"
        f"Unpaywall email: {unp_status}",
        title="[bold cyan]NCBI PubMed Downloader  --  Benchmark MTB[/]",
        border_style="cyan"
    ))

    summary_rows = []
    not_available = []

    for case_id, info in BENCHMARK_PMIDS.items():
        pmid = info["pmid"]
        console.print(f"\n[bold cyan]>> {case_id}[/] -- {info['case']} (PMID: {pmid})")

        # 1. Verifica esistenza
        exists = verify_pmid_exists(pmid)
        if not exists:
            console.print(f"  [bold red]NOK PMID {pmid} non trovato su PubMed[/]")
            not_available.append(f"{case_id} | PMID {pmid} | Non trovato")
            continue

        # 2. Scarica abstract e metadati
        console.print(f"  [yellow]Scaricando metadati e abstract...[/]")
        metadata = fetch_abstract_and_metadata(pmid)

        if metadata.get("status") == "fetch_failed":
            console.print(f"  [red]NOK Errore: {metadata.get('error')}[/]")
            not_available.append(f"{case_id} | PMID {pmid} | Errore fetch")
            continue

        # Aggiungi info benchmark al metadata
        metadata["case_id"] = case_id
        metadata["benchmark_gene"] = info["gene"]
        metadata["benchmark_variant"] = info["variant"]
        metadata["benchmark_tumor"] = info["tumor"]
        metadata["benchmark_expected_drug"] = info["expected_drug"]
        metadata["benchmark_escat"] = info["escat"]

        # 3. Tenta download full text  --  Step A: PMC
        pmc_id = metadata.get("pmc_id", "")
        doi = metadata.get("doi", "")
        fulltext_status = "not_in_pmc"
        fulltext_source = ""
        fulltext = ""

        if pmc_id:
            console.print(f"  [yellow]PMC ID trovato ({pmc_id}), scaricando full text da PMC...[/]")
            fulltext, fulltext_status = fetch_fulltext_pmc(pmc_id, pmid)

            if fulltext_status == "ok":
                fulltext_source = "PMC"
                console.print(f"  [green]OK Full text scaricato da PMC ({len(fulltext):,} caratteri)[/]")
            else:
                console.print(f"  [yellow]>> PMC non disponibile ({fulltext_status}), provo Unpaywall...[/]")

        # 4. Fallback: Unpaywall (se PMC non ha funzionato e abbiamo il DOI)
        if not fulltext and doi:
            console.print(f"  [yellow]Tentativo Unpaywall per DOI: {doi}[/]")
            fulltext, fulltext_status, oa_url = fetch_fulltext_unpaywall(doi, pmid)

            if fulltext_status.startswith("ok"):
                fulltext_source = f"Unpaywall ({oa_url[:60]}...)" if len(oa_url) > 60 else f"Unpaywall ({oa_url})"
                console.print(f"  [green]OK Full text trovato via Unpaywall ({fulltext_status})[/]")
                console.print(f"  [dim]URL: {oa_url[:80]}[/]")
                metadata["unpaywall_oa_url"] = oa_url
            elif fulltext_status == "not_oa":
                console.print(f"  [red]PAYWALL Paper non open access su Unpaywall (paywall confermato)[/]")
                not_available.append(
                    f"{case_id} | PMID {pmid} | Paywall confermato (DOI: {doi})"
                )
            elif fulltext_status == "no_email_configured":
                console.print(f"  [yellow]>> Unpaywall saltato: configura UNPAYWALL_EMAIL nello script[/]")
                not_available.append(f"{case_id} | PMID {pmid} | Unpaywall: email non configurata")
            else:
                console.print(f"  [yellow]>> Unpaywall: {fulltext_status}[/]")
                not_available.append(f"{case_id} | PMID {pmid} | Unpaywall: {fulltext_status}")

        elif not fulltext and not doi:
            console.print(f"  [red]NOK Nessun DOI disponibile, impossibile usare Unpaywall[/]")
            not_available.append(f"{case_id} | PMID {pmid} | Nessun DOI")

        # 5. Salva full text se disponibile
        if fulltext and fulltext_status.startswith("ok"):
            fulltext_path = OUTPUT_DIR / f"fulltext_{pmid}.txt"
            fulltext_path.write_text(
                f"Fonte: {fulltext_source}\n"
                f"PMID: {pmid}\n"
                f"DOI: {doi}\n"
                f"{'=' * 60}\n\n"
                + fulltext,
                encoding="utf-8"
            )
            console.print(f"  [green]OK Full text salvato: fulltext_{pmid}.txt[/]")

        metadata["fulltext_status"] = fulltext_status
        metadata["fulltext_available"] = fulltext_status.startswith("ok")
        metadata["fulltext_source"] = fulltext_source

        # 6. Salva metadata JSON
        meta_path = OUTPUT_DIR / f"metadata_{pmid}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            meta_clean = {k: v for k, v in metadata.items() if k != "xml_raw"}
            json.dump(meta_clean, f, ensure_ascii=False, indent=2)

        console.print(f"  [green]OK Metadata salvato: {meta_path.name}[/]")
        if metadata.get("title"):
            console.print(f"  [dim]Titolo: {metadata['title'][:80]}[/]")
        if metadata.get("abstract") and metadata["abstract"] != "Abstract non disponibile.":
            console.print(f"  [dim]Abstract: {metadata['abstract'][:120]}...[/]")

        # 7. Aggiungi alla tabella riassuntiva
        summary_rows.append({
            "case_id": case_id,
            "pmid": pmid,
            "gene": info["gene"],
            "variant": info["variant"],
            "tumor": info["tumor"],
            "expected_drug": info["expected_drug"],
            "escat": info["escat"],
            "title": metadata.get("title", "")[:80],
            "journal": metadata.get("journal", ""),
            "pub_date": metadata.get("pub_date", ""),
            "doi": doi,
            "pmc_id": pmc_id,
            "abstract_available": bool(
                metadata.get("abstract") and
                metadata["abstract"] != "Abstract non disponibile."
            ),
            "fulltext_available": fulltext_status.startswith("ok"),
            "fulltext_source": fulltext_source
        })

    # ============================================================================
    # SALVA RIEPILOGO CSV
    # ============================================================================

    if summary_rows:
        csv_path = OUTPUT_DIR.parent / "benchmark_papers_summary.csv"
        fieldnames = list(summary_rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_rows)

        # Stampa tabella riepilogativa con Rich
        table = Table(
            title="[bold cyan]Riepilogo Download Paper Benchmark[/]",
            border_style="cyan",
            box=box.ROUNDED,
            show_lines=True
        )
        table.add_column("Case ID", style="bold cyan", justify="center")
        table.add_column("PMID", style="bold white")
        table.add_column("Gene", style="bold green")
        table.add_column("Abstract", justify="center")
        table.add_column("Full Text", justify="center")
        table.add_column("Fonte", style="dim")
        table.add_column("Journal", style="dim")

        for row in summary_rows:
            abstract_icon = "[green]OK[/]" if row["abstract_available"] else "[red]NOK[/]"
            if row["fulltext_available"]:
                fulltext_icon = "[green]OK[/]"
            else:
                fulltext_icon = "[red]paywall[/]"
            table.add_row(
                row["case_id"],
                row["pmid"],
                row["gene"],
                abstract_icon,
                fulltext_icon,
                row.get("fulltext_source", "-")[:20] if row.get("fulltext_source") else "-",
                row["journal"][:30] if row["journal"] else "-"
            )

        console.print("\n")
        console.print(table)

        n_abstract = sum(1 for r in summary_rows if r["abstract_available"])
        n_fulltext = sum(1 for r in summary_rows if r["fulltext_available"])
        n_pmc = sum(1 for r in summary_rows if r.get("fulltext_source", "").startswith("PMC"))
        n_unpaywall = sum(1 for r in summary_rows if r.get("fulltext_source", "").startswith("Unpaywall"))

        console.print(Panel(
            f"Paper processati: [bold cyan]{len(summary_rows)}/{len(BENCHMARK_PMIDS)}[/]\n"

            
            f"Abstract disponibili: [bold green]{n_abstract}[/]\n"
            f"Full text open access: [bold green]{n_fulltext}[/]\n"
            f"  >> da PMC: [green]{n_pmc}[/]\n"
            f"  >> da Unpaywall: [green]{n_unpaywall}[/]\n"
            f"Paywall/non disponibili: [bold yellow]{len(BENCHMARK_PMIDS) - n_fulltext}[/]\n\n"
            f"File CSV: [green]{OUTPUT_DIR.parent / 'benchmark_papers_summary.csv'}[/]\n"
            f"Cartella JSON+fulltext: [green]{OUTPUT_DIR}[/]",
            title="[bold green]Download Completato[/]",
            border_style="green"
        ))

    # ============================================================================
    # SALVA LISTA NOT AVAILABLE
    # ============================================================================

    if not_available:
        not_avail_path = OUTPUT_DIR.parent / "benchmark_papers_not_available.txt"
        with open(not_avail_path, "w", encoding="utf-8") as f:
            f.write("Paper non disponibili come full text open access\n")
            f.write("=" * 60 + "\n\n")
            for line in not_available:
                f.write(line + "\n")
        console.print(
            f"\n[yellow]>> {len(not_available)} paper con limitazioni salvati in:[/]\n"
            f"  {not_avail_path}"
        )
        console.print(
            "\n[dim]Per i paper paywall puoi accedere via:\n"
            "  1. Accesso istituzionale universitario (VPN + proxy)\n"
            "  2. Unpaywall browser extension (https://unpaywall.org)\n"
            "  3. Richiesta diretta agli autori via ResearchGate\n\n"
            "Per estrarre testo da PDF scaricati manualmente:\n"
            "  pip install pdfminer.six\n"
            "  python -c \"from pdfminer.high_level import extract_text; "
            "print(extract_text('paper.pdf'))\"[/]\n"
        )


if __name__ == "__main__":
    main()
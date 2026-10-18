"""Read-only document resolution and deterministic source-unit parsers."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import csv
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .models import SourceUnit
from .sentence_spans import sentence_spans


AVAILABILITY = {
    "NO_DOCUMENT_IDENTIFIER", "METADATA_ONLY", "ABSTRACT_AVAILABLE",
    "PMC_XML_AVAILABLE", "LOCAL_PDF_AVAILABLE", "FULLTEXT_AVAILABLE",
    "DOCUMENT_UNAVAILABLE", "RIGHTS_RESTRICTED", "RESOLUTION_FAILED",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class DocumentRecord:
    document_id: str
    identifiers: dict
    availability: str
    title: str | None = None
    abstract: str | None = None
    abstract_sections: list = None
    full_text_format: str | None = None
    local_path: str | None = None
    retrieved_at: str | None = None
    content_hash: str | None = None
    license: str | None = None
    resolver: str = "offline/local-only"
    errors: list = None

    def to_dict(self):
        value = asdict(self)
        value["abstract_sections"] = value["abstract_sections"] or []
        value["errors"] = value["errors"] or []
        return value


class DocumentResolver:
    """Resolve only local metadata and explicitly supplied local documents.

    No network call is made. A PMID in a publication index yields metadata only;
    it never becomes an abstract or full-text record without local content.
    """

    def __init__(self, publication_csv=None, local_records=None):
        self.publications = {}
        if publication_csv:
            with Path(publication_csv).open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    pmid = row.get("pmid", "").strip()
                    if pmid:
                        self.publications[f"pmid:{pmid}"] = row
        self.local_records = local_records or {}

    def resolve(self, identifier: dict | None) -> dict:
        identifier = identifier or {}
        pmid = str(identifier.get("pmid", "")).strip() or None
        doi = str(identifier.get("doi", "")).strip() or None
        nct = str(identifier.get("nct", "")).strip() or None
        url = str(identifier.get("url", "")).strip() or None
        local_path = identifier.get("local_path")
        if local_path and Path(local_path).is_file():
            path = Path(local_path)
            fmt = "PDF" if path.suffix.lower() == ".pdf" else path.suffix.lower().lstrip(".")
            content = path.read_bytes()
            return DocumentRecord(
                document_id=f"local:{_sha(str(path.resolve()))[:24]}",
                identifiers={"pmid": pmid, "pmcid": None, "doi": doi, "nct": nct, "url": url},
                availability="LOCAL_PDF_AVAILABLE" if fmt == "PDF" else "FULLTEXT_AVAILABLE",
                full_text_format=fmt, local_path=str(path), content_hash=hashlib.sha256(content).hexdigest(),
            ).to_dict()
        if pmid and f"pmid:{pmid}" in self.local_records:
            record = dict(self.local_records[f"pmid:{pmid}"])
            abstract = record.get("abstract")
            return DocumentRecord(
                document_id=f"pmid:{pmid}",
                identifiers={"pmid": pmid, "pmcid": record.get("pmcid"), "doi": doi, "nct": nct, "url": url},
                availability="ABSTRACT_AVAILABLE" if abstract else "METADATA_ONLY",
                title=record.get("title"), abstract=abstract,
                abstract_sections=record.get("abstract_sections", []),
                content_hash=_sha(abstract) if abstract else None,
                resolver="offline/local-record",
            ).to_dict()
        if pmid and f"pmid:{pmid}" in self.publications:
            row = self.publications[f"pmid:{pmid}"]
            return DocumentRecord(
                document_id=f"pmid:{pmid}",
                identifiers={"pmid": pmid, "pmcid": None, "doi": doi, "nct": nct, "url": url},
                availability="METADATA_ONLY", title=row.get("citation_text") or None,
            ).to_dict()
        if pmid or doi or nct or url:
            document_id = f"pmid:{pmid}" if pmid else (f"doi:{doi}" if doi else (nct or url))
            return DocumentRecord(
                document_id=document_id,
                identifiers={"pmid": pmid, "pmcid": None, "doi": doi, "nct": nct, "url": url},
                availability="DOCUMENT_UNAVAILABLE", errors=["no local document or metadata record"],
            ).to_dict()
        return DocumentRecord(
            document_id="unresolved:missing-identifier",
            identifiers={"pmid": None, "pmcid": None, "doi": None, "nct": None, "url": None},
            availability="NO_DOCUMENT_IDENTIFIER",
        ).to_dict()


class PubMedAbstractParser:
    parser = "PubMedAbstractParser"
    version = "1.1"

    def parse(self, document_id: str, title: str | None, abstract: str | None):
        units = []
        if title:
            units.append(SourceUnit.from_document_text(
                document_id, "TITLE", title, parser=self.parser, parser_version=self.version,
            ))
        if not abstract:
            return units
        units.append(SourceUnit.from_document_text(
            document_id, "ABSTRACT", abstract, char_start=0, char_end=len(abstract),
            parser=self.parser, parser_version=self.version,
        ))
        heading_pattern = re.compile(r"(?P<head>[A-Z][A-Z /-]{2,}):\s*")
        matches = list(heading_pattern.finditer(abstract))
        sections = []
        if matches:
            for index, match in enumerate(matches):
                start = match.end()
                end = matches[index + 1].start() if index + 1 < len(matches) else len(abstract)
                text = abstract[start:end].strip()
                if text:
                    sections.append((match.group("head").strip(), start, end, text))
        else:
            sections.append((None, 0, len(abstract), abstract))
        for section, start, end, text in sections:
            if section:
                units.append(SourceUnit.from_document_text(
                    document_id, "ABSTRACT_SECTION", text, char_start=start, char_end=end,
                    section=section, parser=self.parser, parser_version=self.version,
                ))
            for sentence_index, (sentence_left, sentence_right) in enumerate(sentence_spans(text)):
                sentence = text[sentence_left:sentence_right]
                if not sentence:
                    continue
                sentence_start = start + sentence_left
                units.append(SourceUnit.from_document_text(
                    document_id, "ABSTRACT_SENTENCE", sentence,
                    char_start=sentence_start, char_end=sentence_start + len(sentence),
                    section=section, sentence_index=sentence_index,
                    parser=self.parser, parser_version=self.version,
                ))
        return units


class JatsXmlParser:
    parser = "JatsXmlParser"
    version = "1.2"

    @staticmethod
    def _local_name(node):
        return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""

    @staticmethod
    def _text(node):
        return " ".join("".join(node.itertext()).split()) if node is not None else ""

    def parse(self, document_id: str, xml_text: str):
        root = ET.fromstring(xml_text)
        units = []
        title = next((node for node in root.iter() if self._local_name(node) == "article-title"), None)
        if title is not None and self._text(title):
            units.append(SourceUnit.from_document_text(document_id, "TITLE", self._text(title),
                                                        parser=self.parser, parser_version=self.version))

        def emit_abstract_paragraph(paragraph, section, paragraph_index):
            text = self._text(paragraph)
            if not text:
                return
            # JATS abstract paragraphs are represented once as complete,
            # independently citable units.  Do not add a second aggregate
            # ABSTRACT unit or sentence copies of the same abstract paragraph.
            units.append(SourceUnit.from_document_text(
                document_id, "ABSTRACT", text, section=section,
                paragraph_index=paragraph_index, parser=self.parser,
                parser_version=self.version,
            ))

        def walk_abstract(node, section=None, paragraph_counts=None):
            paragraph_counts = paragraph_counts if paragraph_counts is not None else {}
            for child in node:
                tag = self._local_name(child)
                if tag == "sec":
                    heading = next((item for item in child if self._local_name(item) == "title"), None)
                    child_section = self._text(heading) or section
                    walk_abstract(child, child_section, paragraph_counts)
                elif tag == "p":
                    paragraph_index = paragraph_counts.get(section, 0)
                    paragraph_counts[section] = paragraph_index + 1
                    emit_abstract_paragraph(child, section, paragraph_index)
                elif tag not in {"title", "label"}:
                    walk_abstract(child, section, paragraph_counts)

        abstracts = [node for node in root.iter() if self._local_name(node) == "abstract"]
        for abstract in abstracts:
            before = len(units)
            walk_abstract(abstract)
            if len(units) == before:
                # A few JATS variants place prose directly under <abstract>.
                text = self._text(abstract)
                if text:
                    units.append(SourceUnit.from_document_text(
                        document_id, "ABSTRACT", text, char_start=0,
                        char_end=len(text), parser=self.parser,
                        parser_version=self.version,
                    ))

        def child_named(node, name):
            return next((child for child in node if self._local_name(child) == name), None)

        def emit_paragraph(paragraph, section, subsection, paragraph_index):
            text = self._text(paragraph)
            if not text:
                return
            units.append(SourceUnit.from_document_text(
                document_id, "FULLTEXT_PARAGRAPH", text, section=section,
                subsection=subsection, paragraph_index=paragraph_index,
                parser=self.parser, parser_version=self.version,
            ))
            for sentence_index, (sentence_start, sentence_end) in enumerate(sentence_spans(text)):
                sentence = text[sentence_start:sentence_end]
                if sentence:
                    units.append(SourceUnit.from_document_text(
                        document_id, "FULLTEXT_SENTENCE", sentence,
                        section=section, subsection=subsection,
                        paragraph_index=paragraph_index,
                        sentence_index=sentence_index, char_start=sentence_start,
                        char_end=sentence_start + len(sentence),
                        parser=self.parser, parser_version=self.version,
                    ))

        paragraph_counts = {}

        def emit_table(table, section, subsection):
            table_id = table.attrib.get("id")
            label = self._text(child_named(table, "label")) or None
            caption = self._text(child_named(table, "caption")) or None
            if caption:
                units.append(SourceUnit.from_document_text(
                    document_id, "TABLE_CAPTION", caption, section=section,
                    subsection=subsection, table_id=table_id, table_label=label,
                    caption=caption, parser=self.parser,
                    parser_version=self.version,
                ))
            for row_index, row in enumerate(
                node for node in table.iter() if self._local_name(node) == "tr"
            ):
                for col_index, cell in enumerate(list(row)):
                    text = self._text(cell)
                    if text:
                        units.append(SourceUnit.from_document_text(
                            document_id, "TABLE_CELL", text, section=section,
                            subsection=subsection, table_id=table_id,
                            table_label=label, row=row_index, column=col_index,
                            parser=self.parser, parser_version=self.version,
                        ))

        def emit_figure(figure, section, subsection):
            figure_id = figure.attrib.get("id")
            label = self._text(child_named(figure, "label")) or None
            caption = self._text(child_named(figure, "caption")) or None
            if caption:
                units.append(SourceUnit.from_document_text(
                    document_id, "FIGURE_CAPTION", caption, section=section,
                    subsection=subsection, figure_id=figure_id,
                    figure_label=label, caption=caption, parser=self.parser,
                    parser_version=self.version,
                ))

        def walk_supplementary(node, section, subsection):
            for child in node:
                tag = self._local_name(child)
                if tag == "caption":
                    text = self._text(child)
                    if text:
                        key = (section, subsection)
                        paragraph_index = paragraph_counts.get(key, 0)
                        paragraph_counts[key] = paragraph_index + 1
                        units.append(SourceUnit.from_document_text(
                            document_id, "SUPPLEMENTARY_CAPTION", text,
                            section=section, subsection=subsection,
                            paragraph_index=paragraph_index, caption=text,
                            parser=self.parser,
                            parser_version=self.version,
                        ))
                elif tag == "p":
                    key = (section, subsection)
                    paragraph_index = paragraph_counts.get(key, 0)
                    paragraph_counts[key] = paragraph_index + 1
                    emit_paragraph(child, section, subsection, paragraph_index)
                elif tag == "table-wrap":
                    emit_table(child, section, subsection)
                elif tag == "fig":
                    emit_figure(child, section, subsection)
                elif tag == "sec":
                    heading = self._text(child_named(child, "title")) or None
                    child_section = section or heading
                    child_subsection = (
                        f"{subsection} / {heading}" if subsection and heading
                        else heading or subsection
                    )
                    if heading:
                        units.append(SourceUnit.from_document_text(
                            document_id, "FULLTEXT_SECTION", heading,
                            section=child_section, subsection=child_subsection,
                            parser=self.parser, parser_version=self.version,
                        ))
                    walk_supplementary(child, child_section, child_subsection)
                else:
                    walk_supplementary(child, section, subsection)

        def walk_body(node, section=None, subsection=None):
            for child in node:
                tag = self._local_name(child)
                if tag == "sec":
                    heading = self._text(child_named(child, "title")) or None
                    if section is None:
                        child_section, child_subsection = heading, None
                    else:
                        child_section, child_subsection = section, (
                            f"{subsection} / {heading}" if subsection and heading
                            else heading or subsection
                        )
                    if heading:
                        units.append(SourceUnit.from_document_text(
                            document_id, "FULLTEXT_SECTION", heading,
                            section=child_section, subsection=child_subsection,
                            parser=self.parser, parser_version=self.version,
                        ))
                    walk_body(child, child_section, child_subsection)
                elif tag == "p":
                    key = (section, subsection)
                    paragraph_index = paragraph_counts.get(key, 0)
                    paragraph_counts[key] = paragraph_index + 1
                    emit_paragraph(child, section, subsection, paragraph_index)
                elif tag == "table-wrap":
                    emit_table(child, section, subsection)
                elif tag == "fig":
                    emit_figure(child, section, subsection)
                elif tag == "supplementary-material":
                    walk_supplementary(child, section, subsection)
                elif tag not in {"title", "label", "caption", "abstract", "ref-list", "back"}:
                    walk_body(child, section, subsection)

        bodies = [node for node in root.iter() if self._local_name(node) == "body"]
        for body in bodies:
            walk_body(body)
        return units


class PdfDocumentParser:
    parser = "PdfDocumentParser"
    version = "1.0"

    def parse(self, document_id: str, path):
        try:
            from pypdf import PdfReader
        except ImportError:
            return [], "pypdf unavailable"
        units = []
        try:
            reader = PdfReader(str(path))
            for page_index, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                for block_index, block in enumerate(re.split(r"\n\s*\n", text)):
                    block = block.strip()
                    if not block:
                        continue
                    units.append(SourceUnit.from_document_text(
                        document_id, "PDF_TEXT_BLOCK", block, page=page_index,
                        parser=self.parser, parser_version=self.version,
                        locator_confidence="TEXT_EXTRACTION",
                    ))
            return units, None
        except Exception as exc:  # pragma: no cover - parser errors are data-dependent
            return [], str(exc)

"""Il selector deve essere deterministico, spiegabile e cieco rispetto al gold.

Le metriche di retrieval dicono quanto bene ordina. Questi test dicono se ci si
può fidare dell'ordine: che non cambi fra due esecuzioni, che non dipenda
dall'ordine in cui le unità arrivano, che non guardi i bundle congelati, e che
non prometta più di quanto il testo contenga — in particolare che la presenza di
un gene non venga scambiata per la presenza di una sua variante.
"""

from __future__ import annotations

import ast
import unicodedata
from pathlib import Path
from unittest import TestCase

from backend.research_pipeline.experimental import sourceunit_selector as sus

_MODULE_PATH = Path(sus.__file__)
_MODULE_SOURCE = _MODULE_PATH.read_text(encoding="utf-8")
_MODULE_AST = ast.parse(_MODULE_SOURCE)


def _imported_modules() -> set[str]:
    """Moduli importati, dai nodi AST: la prosa dei docstring non conta."""
    names: set[str] = set()
    for node in ast.walk(_MODULE_AST):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _identifiers() -> set[str]:
    """Nomi e attributi usati nel codice, esclusi commenti e docstring."""
    names: set[str] = set()
    for node in ast.walk(_MODULE_AST):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names

CANDIDATE = {
    "candidate_id": "GCA-test",
    "disease": [{"label": "Chronic Myeloid Leukemia"}],
    "biomarkers": [{"label": "ABL1", "type": "Gene"},
                   {"label": "V299L", "type": "Variant"}],
    "interventions": [{"label": "dasatinib"}],
    "predicate": "has_evidence_statement",
}


def unit(uid: str, text: str, unit_type: str = "FULLTEXT_PARAGRAPH") -> dict:
    return {"source_unit_id": uid, "document_id": "pmid:1",
            "unit_type": unit_type, "text": text}


def make_input(units, candidate=None) -> sus.SourceUnitSelectionInput:
    return sus.SourceUnitSelectionInput.from_candidate(
        candidate or CANDIDATE, "pmid:1", units)


class ContractTest(TestCase):
    def test_features_are_split_by_biomarker_type(self) -> None:
        """Una variante trattata come gene perderebbe il suo peso."""
        selection = make_input([])
        self.assertEqual(selection.genes, ("ABL1",))
        self.assertEqual(selection.alterations, ("V299L",))
        self.assertEqual(selection.interventions, ("dasatinib",))

    def test_result_carries_everything_needed_to_contest_it(self) -> None:
        result = sus.select(make_input([unit("SU-1", "ABL1 V299L confers dasatinib resistance in CML patients treated for years.")]))
        self.assertEqual(result.status, sus.STATUS_SELECTED)
        self.assertEqual(result.selector_version, sus.SELECTOR_VERSION)
        top = result.ranked_source_units[0]
        for value in (result.input_hash, result.ranking_hash, result.selected_ids_hash):
            self.assertEqual(len(value), 64)
        self.assertIn("ABL1", top.matched_gene)
        self.assertIn("V299L", top.matched_alteration)
        self.assertIn("dasatinib", top.matched_intervention)
        self.assertTrue(top.selection_reason)

    def test_the_selector_never_uses_an_llm(self) -> None:
        """Nessuna dipendenza da un modello: il ranking è aritmetica."""
        imported = " ".join(_imported_modules()).lower()
        for forbidden in ("openai", "ollama", "anthropic", "transformers",
                          "sentence_transformers", "torch", "llm_config",
                          "enricher", "requests", "urllib"):
            self.assertNotIn(forbidden, imported, forbidden)


class LeakageTest(TestCase):
    """§21 — durante l'inferenza il gold non viene mai letto."""

    def test_module_imports_nothing_that_can_reach_the_gold(self) -> None:
        """Il gold vive nei dataset congelati: il selector non li raggiunge."""
        for imported in _imported_modules():
            self.assertNotIn("data_access", imported)
            self.assertNotIn("replay", imported)
            self.assertNotIn("retrieval", imported)
        self.assertTrue(
            all(not name.startswith("backend.") for name in _imported_modules()),
            f"il selector importa moduli del runtime: {sorted(_imported_modules())}",
        )

    def test_no_gold_identifier_appears_in_executable_code(self) -> None:
        """Controlla i nomi usati dal codice, non le parole nei commenti."""
        used = {name.lower() for name in _identifiers()}
        for forbidden in ("source_unit_ids", "evidence_bundles_path", "gold",
                          "author_claim_quote", "support_status", "bundle"):
            self.assertNotIn(forbidden, used, forbidden)

    def test_inference_touches_no_frozen_dataset(self) -> None:
        """§21 — gold_access_count = 0, verificato facendo esplodere l'accesso."""
        from backend.research_pipeline import data_access as da

        accesses: list[str] = []

        def explode(name: str):
            def guard(*_args, **_kwargs):
                accesses.append(name)
                raise AssertionError(f"il selector ha letto {name}")
            return guard

        originals = {name: getattr(da, name) for name in
                     ("read_jsonl", "iter_jsonl", "load_source_unit_index",
                      "evidence_bundles_path", "candidates_path")}
        for name in originals:
            setattr(da, name, explode(name))
        try:
            units = [unit("SU-1", "ABL1 V299L confers dasatinib resistance in CML patients."),
                     unit("SU-2", "Unrelated methodological background about the study centre.")]
            result = sus.select(make_input(units), top_k=2)
            self.assertEqual(result.status, sus.STATUS_SELECTED)
        finally:
            for name, original in originals.items():
                setattr(da, name, original)
        self.assertEqual(accesses, [])

    def test_selection_input_carries_only_candidate_and_units(self) -> None:
        allowed = {"candidate_id", "document_id", "disease", "genes", "alterations",
                   "interventions", "graph_relation", "source_units"}
        self.assertEqual(set(sus.SourceUnitSelectionInput.__dataclass_fields__), allowed)


class DeterminismTest(TestCase):
    """§20 — stesso input, stesso ranking. Dieci volte."""

    UNITS = [
        unit("SU-b", "ABL1 V299L was detected after dasatinib therapy in this cohort of patients."),
        unit("SU-a", "Chronic Myeloid Leukemia responds to imatinib in most newly diagnosed cases."),
        unit("SU-c", "No mutation was identified in the kinase domain of the analysed samples."),
        unit("SU-d", "dasatinib", "TABLE_CELL"),
    ]

    def test_ten_repetitions_produce_the_same_ranking(self) -> None:
        first = sus.select(make_input(self.UNITS), top_k=3)
        for _ in range(10):
            again = sus.select(make_input(self.UNITS), top_k=3)
            self.assertEqual(again.ranking_hash, first.ranking_hash)
            self.assertEqual(again.selected_source_unit_ids, first.selected_source_unit_ids)
            self.assertEqual(again.selection_scores, first.selection_scores)

    def test_input_order_does_not_change_the_ranking(self) -> None:
        """§35 — permutare l'input non deve cambiare l'esito."""
        base = sus.select(make_input(self.UNITS), top_k=3)
        for shift in range(1, len(self.UNITS)):
            rotated = self.UNITS[shift:] + self.UNITS[:shift]
            self.assertEqual(sus.select(make_input(rotated), top_k=3).ranking_hash,
                             base.ranking_hash)

    def test_ties_are_broken_by_source_unit_id(self) -> None:
        units = [unit("SU-z", "irrelevant filler text about unrelated topics entirely here."),
                 unit("SU-a", "another irrelevant filler text about unrelated topics here.")]
        ranked = sus.rank(make_input(units))
        self.assertEqual(ranked[0].score_total, ranked[1].score_total)
        self.assertEqual([u.source_unit_id for u in ranked], ["SU-a", "SU-z"])


class NormalizationTest(TestCase):
    """§4 e §35 — la forma non deve contare, il contenuto sì."""

    def test_case_and_punctuation_do_not_change_matching(self) -> None:
        a = sus.match_features("ABL1 V299L, dasatinib.", make_input([]))
        b = sus.match_features("abl1 v299l -- DASATINIB!", make_input([]))
        self.assertEqual(a, b)

    def test_nfc_and_nfd_are_equivalent(self) -> None:
        text = "Résistance to dasatinib in ABL1 V299L"
        nfd = unicodedata.normalize("NFD", text)
        self.assertNotEqual(text, nfd)
        self.assertEqual(sus.normalize_text(text), sus.normalize_text(nfd))

    def test_hgvs_prefix_is_notation_not_substance(self) -> None:
        self.assertEqual(sus.normalize_alteration("p.V299L"), sus.normalize_alteration("V299L"))
        self.assertNotEqual(sus.normalize_alteration("V299L"), sus.normalize_alteration("V299M"))

    def test_no_semantic_expansion(self) -> None:
        """"EGFR mutation" non deve diventare "EGFR L858R"."""
        candidate = {**CANDIDATE, "biomarkers": [{"label": "EGFR", "type": "Gene"},
                                                 {"label": "L858R", "type": "Variant"}]}
        matches = sus.match_features("EGFR mutation was present in the tumour sample.",
                                     make_input([], candidate))
        self.assertEqual(matches["gene"], ("EGFR",))
        self.assertEqual(matches["alteration"], ())


class ClinicalDiscriminationTest(TestCase):
    def test_gene_presence_is_not_alteration_presence(self) -> None:
        """§16 — il gene c'è, la variante no: non devono equivalersi."""
        matches = sus.match_features(
            "ABL1 kinase domain mutations were analysed in all enrolled patients.",
            make_input([]))
        self.assertEqual(matches["gene"], ("ABL1",))
        self.assertEqual(matches["alteration"], ())

    def test_alteration_beats_drug_only_units(self) -> None:
        """§17 — un'unità che parla solo del farmaco non deve superarne una completa."""
        units = [
            unit("SU-drug", "dasatinib was administered daily and dasatinib exposure was monitored "
                            "throughout the study period in all treated participants."),
            unit("SU-full", "ABL1 V299L emerged during dasatinib therapy and conferred resistance "
                            "in these chronic myeloid leukemia patients."),
        ]
        ranked = sus.rank(make_input(units))
        self.assertEqual(ranked[0].source_unit_id, "SU-full")

    def test_a_bare_alteration_does_not_win_without_context(self) -> None:
        """§19 — "V299L" da solo è un'occorrenza, non un'affermazione."""
        units = [
            unit("SU-bare", "V299L", "TABLE_CELL"),
            unit("SU-context", "The V299L substitution was identified in three patients with "
                               "chronic myeloid leukemia after dasatinib exposure."),
        ]
        ranked = sus.rank(make_input(units))
        self.assertEqual(ranked[0].source_unit_id, "SU-context")
        bare = next(u for u in ranked if u.source_unit_id == "SU-bare")
        self.assertLess(bare.context_factor, 1.0)

    def test_table_units_are_not_excluded_a_priori(self) -> None:
        """§18 — un biomarcatore può comparire solo in tabella."""
        units = [unit("SU-table", "ABL1 V299L detected in 3 of 12 dasatinib-treated patients.",
                      "TABLE_CELL"),
                 unit("SU-other", "Patients were followed for a median of twelve months overall.")]
        result = sus.select(make_input(units), top_k=1)
        self.assertEqual(result.selected_source_unit_ids, ("SU-table",))


class EdgeCaseTest(TestCase):
    """§35 — l'input reale contiene unità vuote, duplicate e senza testo."""

    def test_units_without_text_do_not_crash_and_do_not_win(self) -> None:
        units = [unit("SU-empty", ""), unit("SU-none", None),
                 unit("SU-ok", "ABL1 V299L confers dasatinib resistance in CML patients.")]
        result = sus.select(make_input(units), top_k=3)
        self.assertEqual(result.ranked_source_units[0].source_unit_id, "SU-ok")
        self.assertNotIn("SU-empty", result.selected_source_unit_ids)
        self.assertNotIn("SU-none", result.selected_source_unit_ids)

    def test_duplicate_texts_keep_a_stable_order(self) -> None:
        text = "ABL1 V299L confers dasatinib resistance in chronic myeloid leukemia."
        units = [unit("SU-2", text), unit("SU-1", text)]
        ranked = sus.rank(make_input(units))
        self.assertEqual([u.source_unit_id for u in ranked], ["SU-1", "SU-2"])

    def test_an_empty_document_yields_no_relevant_source_unit(self) -> None:
        """§24 — meglio nessuna unità che la meno peggio."""
        result = sus.select(make_input([]))
        self.assertEqual(result.status, sus.STATUS_NO_RELEVANT)
        self.assertEqual(result.selected_source_unit_ids, ())

    def test_a_document_without_any_signal_yields_no_relevant_source_unit(self) -> None:
        units = [unit("SU-x", "The weather in the study region was recorded daily by staff."),
                 unit("SU-y", "Participants completed a questionnaire about dietary habits.")]
        result = sus.select(make_input(units))
        self.assertEqual(result.status, sus.STATUS_NO_RELEVANT)

    def test_selection_never_invents_a_source_unit(self) -> None:
        units = [unit("SU-1", "ABL1 V299L and dasatinib in chronic myeloid leukemia patients."),
                 unit("SU-2", "Unrelated background about laboratory procedures and staffing.")]
        result = sus.select(make_input(units), top_k=10)
        offered = {u["source_unit_id"] for u in units}
        self.assertTrue(set(result.selected_source_unit_ids) <= offered)


class SeparationFromRuntimeTest(TestCase):
    """Il modulo è sperimentale: nulla nel runtime canonico lo importa."""

    def test_no_runtime_module_imports_the_selector(self) -> None:
        package = Path(sus.__file__).resolve().parents[1]
        importers = [
            path for path in package.rglob("*.py")
            if "experimental" not in path.parts and "tests" not in path.parts
            and "sourceunit_selector" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(importers, [])

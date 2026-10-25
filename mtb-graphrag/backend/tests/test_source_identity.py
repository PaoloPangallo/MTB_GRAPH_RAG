"""Normalizzazione degli identificatori e identita' delle fonti."""

from __future__ import annotations

import unittest

from backend.pipeline.evidence.source_identity import (
    DOI,
    NCT,
    PMID,
    SourceIdentityResolver,
    build_identifier,
    identifiers_from_source_reference,
    norm_doi,
    norm_doi_set,
    titles_are_similar,
)


class TestDoiNormalization(unittest.TestCase):
    def test_case_is_irrelevant(self) -> None:
        """I DOI sono case-insensitive per specifica: fonderli e' obbligatorio."""
        upper = norm_doi("10.1056/NEJMoa1713137")
        lower = norm_doi("10.1056/nejmoa1713137")
        self.assertTrue(upper.valid and lower.valid)
        self.assertEqual(upper.text, lower.text)

    def test_resolver_prefixes_are_stripped(self) -> None:
        for raw in (
            "https://doi.org/10.1056/nejmoa1713137",
            "http://dx.doi.org/10.1056/nejmoa1713137",
            "doi:10.1056/nejmoa1713137",
            "  10.1056/nejmoa1713137  ",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(norm_doi(raw).text, "10.1056/nejmoa1713137")

    def test_malformed_doi_is_rejected_not_guessed(self) -> None:
        for raw in ("not-a-doi", "11.1234/x", "10.12/x", ""):
            with self.subTest(raw=raw):
                self.assertFalse(norm_doi(raw).valid)

    def test_original_value_is_preserved(self) -> None:
        normalized = norm_doi("HTTPS://DOI.ORG/10.1000/ABC")
        self.assertEqual(normalized.raw, "HTTPS://DOI.ORG/10.1000/ABC")
        self.assertEqual(normalized.text, "10.1000/abc")

    def test_set_deduplicates_equivalent_forms(self) -> None:
        values = norm_doi_set(
            ["10.1056/NEJMoa1713137", "https://doi.org/10.1056/nejmoa1713137"]
        )
        self.assertEqual(values, ("10.1056/nejmoa1713137",))


class TestIdentifierNormalization(unittest.TestCase):
    def test_pmid_accepts_string_and_number(self) -> None:
        as_text = build_identifier(PMID, "30892989")
        as_number = build_identifier(PMID, 30892989)
        self.assertEqual(as_text.text, as_number.text)
        self.assertTrue(as_text.valid)

    def test_pmid_leading_zeros_are_stripped(self) -> None:
        self.assertEqual(build_identifier(PMID, "0022277784").text, "22277784")

    def test_nct_is_upper_cased_and_prefixed(self) -> None:
        self.assertEqual(build_identifier(NCT, "nct02924376").text, "NCT02924376")
        self.assertEqual(build_identifier(NCT, "02924376").text, "NCT02924376")

    def test_malformed_identifier_is_invalid_but_kept(self) -> None:
        identifier = build_identifier(PMID, "abc")
        self.assertFalse(identifier.valid)
        self.assertEqual(identifier.raw, "abc")


class TestSourceIdentityResolver(unittest.TestCase):
    def test_shared_identifier_merges_into_one_source(self) -> None:
        resolver = SourceIdentityResolver()
        resolver.add(identifiers=[build_identifier(PMID, "1234567")], title="uno")
        resolver.add(
            identifiers=[build_identifier(PMID, "1234567"), build_identifier(DOI, "10.1000/x")],
            title="due",
        )
        identities = resolver.identities()
        self.assertEqual(len(identities), 1)
        self.assertEqual(identities[0].pmids, ("1234567",))
        self.assertEqual(identities[0].dois, ("10.1000/x",))
        self.assertTrue(identities[0].is_multi_identifier)

    def test_similar_titles_never_merge(self) -> None:
        """Il titolo non decide mai. Un falso positivo fonderebbe due studi."""
        resolver = SourceIdentityResolver()
        resolver.add(identifiers=[build_identifier(PMID, "111")], title="FLAURA primary analysis")
        resolver.add(identifiers=[build_identifier(PMID, "222")], title="FLAURA primary analysis")
        self.assertEqual(len(resolver.identities()), 2)

    def test_title_similarity_is_diagnostic_only(self) -> None:
        self.assertTrue(titles_are_similar("FLAURA  Primary Analysis", "flaura primary analysis"))
        self.assertFalse(titles_are_similar("", ""))

    def test_merge_is_transitive_through_controlled_identifiers(self) -> None:
        resolver = SourceIdentityResolver()
        resolver.add(identifiers=[build_identifier(PMID, "1"), build_identifier(DOI, "10.1000/a")])
        resolver.add(identifiers=[build_identifier(DOI, "10.1000/a"), build_identifier(NCT, "NCT00000001")])
        identities = resolver.identities()
        self.assertEqual(len(identities), 1)
        self.assertEqual(identities[0].ncts, ("NCT00000001",))

    def test_group_lookup_survives_a_later_merge(self) -> None:
        """Il gruppo restituito da `add` puo' diventare stale; la chiave no."""
        resolver = SourceIdentityResolver()
        resolver.add(identifiers=[build_identifier(PMID, "1")])
        resolver.add(identifiers=[build_identifier(DOI, "10.1000/a")])
        resolver.add(
            identifiers=[build_identifier(PMID, "1"), build_identifier(DOI, "10.1000/a")]
        )
        self.assertEqual(len(resolver.identities()), 1)
        for key in ("pmid:1", "doi:10.1000/a"):
            with self.subTest(key=key):
                self.assertIsNotNone(resolver.resolve_key(key))

    def test_unresolved_source_stays_isolated(self) -> None:
        resolver = SourceIdentityResolver()
        resolver.add(identifiers=[build_identifier(PMID, "nope")], title="senza identificatore")
        resolver.add(identifiers=[build_identifier(PMID, "also-nope")], title="senza identificatore")
        identities = resolver.identities()
        self.assertEqual(len(identities), 2)
        self.assertFalse(any(identity.is_resolved for identity in identities))

    def test_canonical_id_does_not_depend_on_insertion_order(self) -> None:
        forward = SourceIdentityResolver()
        forward.add(identifiers=[build_identifier(DOI, "10.1000/a")])
        forward.add(identifiers=[build_identifier(PMID, "9"), build_identifier(DOI, "10.1000/a")])

        backward = SourceIdentityResolver()
        backward.add(identifiers=[build_identifier(PMID, "9")])
        backward.add(identifiers=[build_identifier(DOI, "10.1000/a"), build_identifier(PMID, "9")])

        self.assertEqual(
            forward.identities()[0].canonical_source_id,
            backward.identities()[0].canonical_source_id,
        )

    def test_pmid_wins_over_doi_in_canonical_id(self) -> None:
        resolver = SourceIdentityResolver()
        resolver.add(
            identifiers=[build_identifier(DOI, "10.1000/a"), build_identifier(PMID, "5")]
        )
        self.assertEqual(resolver.identities()[0].canonical_source_id, "PMID:5")


class TestSourceReferenceExtraction(unittest.TestCase):
    def test_type_comes_from_the_declared_field(self) -> None:
        identifiers = identifiers_from_source_reference(
            {"source_type": "pubmed", "external_identifier": "30892989"}
        )
        self.assertEqual(identifiers[0].kind, PMID)

    def test_source_id_prefix_is_not_treated_as_the_value(self) -> None:
        identifiers = identifiers_from_source_reference(
            {"source_type": "pubmed", "source_id": "PUBMED:30892989"}
        )
        self.assertEqual(identifiers[0].text, "30892989")

    def test_doi_reference_is_recognised(self) -> None:
        identifiers = identifiers_from_source_reference(
            {"source_type": "doi", "external_identifier": "10.1200/JCO.2017.1"}
        )
        self.assertEqual(identifiers[0].kind, DOI)
        self.assertTrue(identifiers[0].valid)

    def test_empty_reference_yields_nothing(self) -> None:
        self.assertEqual(identifiers_from_source_reference({"source_type": "pubmed"}), [])


if __name__ == "__main__":
    unittest.main()

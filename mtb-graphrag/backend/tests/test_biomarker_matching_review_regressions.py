from __future__ import annotations

from backend.pipeline.evidence.qualified_retrieval_query import QueryBiomarker
from backend.pipeline.evidence.qualified_retriever import match_biomarker


def _statement(
    *,
    gene: str,
    label: str,
    components: tuple[str, ...],
    alteration_type: str = "unknown",
    is_compound: bool = False,
) -> dict[str, object]:
    return {
        "biomarker": {
            "gene": gene,
            "label": label,
            "component_biomarkers": list(components),
            "is_compound": is_compound,
        },
        "alteration_type": alteration_type,
    }


def test_multiple_biomarkers_cannot_cross_pair_gene_and_alteration() -> None:
    query = (
        QueryBiomarker(gene="ALK", alteration="G1202R"),
        QueryBiomarker(gene="EGFR", alteration="L858R"),
    )
    crossed = _statement(
        gene="ALK",
        label="ALK L858R",
        components=("L858R",),
    )
    requested = _statement(
        gene="EGFR",
        label="EGFR L858R",
        components=("L858R",),
    )
    assert not match_biomarker(query, crossed).matched
    assert match_biomarker(query, requested).matched


def test_single_variant_does_not_match_compound_variant() -> None:
    query = (QueryBiomarker(gene="ALK", alteration="G1202R (single mutation)"),)
    compound = _statement(
        gene="ALK",
        label="ALK G1202R AND ALK L1196M",
        components=("G1202R", "L1196M"),
        is_compound=True,
    )
    assert not match_biomarker(query, compound).matched


def test_compound_query_requires_the_complete_variant_set() -> None:
    query = (QueryBiomarker(gene="ALK", alteration="G1202R plus L1196M"),)
    single = _statement(
        gene="ALK",
        label="ALK G1202R",
        components=("G1202R",),
    )
    compound = _statement(
        gene="ALK",
        label="ALK G1202R AND ALK L1196M",
        components=("G1202R", "L1196M"),
        is_compound=True,
    )
    assert not match_biomarker(query, single).matched
    assert match_biomarker(query, compound).matched


def test_deletion_shape_is_not_collapsed_to_shared_protein_token() -> None:
    query = (QueryBiomarker(gene="ALK", alteration="G1202R/del"),)
    single = _statement(
        gene="ALK",
        label="ALK G1202R",
        components=("G1202R",),
    )
    deletion = _statement(
        gene="ALK",
        label="ALK G1202R del",
        components=("G1202R/del",),
        alteration_type="deletion",
    )
    assert not match_biomarker(query, single).matched
    assert match_biomarker(query, deletion).matched


def test_gene_prefix_is_removed_for_exact_generic_alteration() -> None:
    query = (QueryBiomarker(gene="EGFR", alteration="exon 19 deletion"),)
    statement = _statement(
        gene="EGFR",
        label="EGFR Exon 19 Deletion",
        components=("EGFR Exon 19 Deletion",),
        alteration_type="deletion",
    )
    assert match_biomarker(query, statement).matched

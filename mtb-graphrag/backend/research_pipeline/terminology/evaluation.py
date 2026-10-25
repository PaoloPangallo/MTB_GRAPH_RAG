"""Explicit denominators; synthetic probes never become independent validation."""
import time


def evaluate(rows, strategies):
    groups, identifiers = {}, set()
    for row in rows:
        if row["id"] in identifiers:
            raise ValueError("Duplicate annotation id")
        identifiers.add(row["id"])
        if row.get("split") not in {"development", "test"} or not isinstance(row.get("expected_entities"), list):
            raise ValueError("Invalid annotation schema")
        group = row.get("concept_group")
        if group and group in groups and groups[group] != row["split"]:
            raise ValueError("Concept-family split leakage")
        if group:
            groups[group] = row["split"]
        if not row.get("annotation_sources"):
            raise ValueError("Annotation source missing")
        if row.get("independence") and row.get("review_status") != "INDEPENDENTLY_REVIEWED":
            raise ValueError("Independent annotation has not been reviewed")
    report = {"schema_version": "entity-resolution-evaluation/1.0", "clinical_validation": False,
              "semantic_admission_enabled": False, "provider_calls": 0,
              "candidate_branch_metrics": {"status": "UNAVAILABLE", "reason": "NO_INDEPENDENT_CANDIDATE_GOLD"},
              "memory_measurement": {"status": "NOT_MEASURED"}}
    for section, independent in (("independent_evaluation", True), ("regression_probes", False)):
        subset = [r for r in rows if bool(r.get("independence")) == independent]
        output = {"sample_count": len(subset), "status": "AVAILABLE" if subset else "NO_ANNOTATIONS", "strategies": {}}
        for name, strategy in strategies.items():
            tp = fp = fn = abstained = hits = gold_count = 0
            cases = []
            started = time.perf_counter()
            for row in subset:
                prediction = strategy(row)
                actual, gold = set(prediction.get("concept_ids", [])), set(row["expected_entities"])
                proposals = list(dict.fromkeys(p["concept_id"] for p in prediction.get("proposals", [])))
                tp += len(actual & gold)
                fp += len(actual - gold)
                fn += len(gold - actual)
                abstained += not actual
                hits += len(gold & set(proposals[:10]))
                gold_count += len(gold)
                cases.append({"id": row["id"], "language": row["language"], "split": row["split"],
                              "expected": sorted(gold), "predicted": sorted(actual),
                              "missing": sorted(gold-actual), "unexpected": sorted(actual-gold),
                              "status": prediction.get("status"), "adversarial_class": row.get("adversarial_class")})
            output["strategies"][name] = {"true_positive": tp, "false_positive": fp, "false_negative": fn,
                "precision_denominator": tp+fp, "recall_denominator": tp+fn,
                "precision": tp/(tp+fp) if tp+fp else None, "recall": tp/(tp+fn) if tp+fn else None,
                "abstention_rate": abstained/len(subset) if subset else None,
                "coverage": (len(subset)-abstained)/len(subset) if subset else None,
                "proposal_recall_at_10": hits/gold_count if gold_count else None,
                "latency_ms": (time.perf_counter()-started)*1000, "cases": cases}
        report[section] = output
    return report

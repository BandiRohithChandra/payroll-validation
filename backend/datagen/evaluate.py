"""Compares validation findings with ground truth, per rule."""
from collections import defaultdict


def evaluate(findings, truth):
    flagged, expected = defaultdict(set), defaultdict(set)
    for f in findings:
        flagged[f["rule_id"]].add(f["record_id"])
    for t in truth:
        expected[t["expected_rule"]].add(t["record_id"])
    rows = []
    for rule in sorted(set(flagged) | set(expected)):
        tp = len(flagged[rule] & expected[rule])
        fp = len(flagged[rule] - expected[rule])
        fn = len(expected[rule] - flagged[rule])
        rows.append({"rule_id": rule, "expected": len(expected[rule]),
                     "flagged": len(flagged[rule]), "tp": tp, "fp": fp, "fn": fn,
                     "precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
                     "recall": round(tp / (tp + fn), 4) if tp + fn else 1.0})
    return rows
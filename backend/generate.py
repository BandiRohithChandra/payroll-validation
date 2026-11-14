"""Generator entry point.
  python generate.py --scale starter --verify
  python generate.py --scale full --formats csv,sql --verify"""
import argparse
import json
import tempfile
from pathlib import Path

import config
from datagen.evaluate import evaluate
from datagen.pipeline import build_dataset
from datagen.validate_dataset import run_checks
from datagen.workflow import summarize
from datagen.writer import DEFAULT_OUT, write_all


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", choices=sorted(config.SCALES), default="starter")
    p.add_argument("--seed", type=int, default=config.SEED)
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--formats", default="csv,json,sql")
    p.add_argument("--verify", action="store_true", help="regenerate twice and compare checksums")
    a = p.parse_args()
    formats = tuple(f for f in a.formats.split(",") if f)
    out = Path(a.out) / a.scale

    data = build_dataset(a.scale, a.seed)
    checks = run_checks(data)
    manifest = write_all(data, out, a.scale, a.seed, formats)
    summary = {
        "scale": a.scale, "seed": a.seed, "row_counts": manifest["tables"],
        "ground_truth_rows": len(data["truth"]),
        "checks": checks, "all_checks_passed": all(c["passed"] for c in checks),
        "rule_evaluation": evaluate(data["findings"], data["truth"]),
        "workflow": summarize(data["payroll_inputs"], data["exceptions"], data["payroll_exports"]),
    }
    with open(out / "validation_summary.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=2)

    print(summary["row_counts"])
    for c in checks:
        print(("PASS " if c["passed"] else "FAIL ") + c["check"],
              "" if c["passed"] else f"{c['failures']} e.g. {c['examples']}")
    print("workflow:", summary["workflow"])

    if a.verify:
        runs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                runs.append(write_all(build_dataset(a.scale, a.seed), Path(tmp) / a.scale,
                                      a.scale, a.seed, formats)["files"])
        identical = runs[0] == runs[1] == manifest["files"]
        with open(out / "reproducibility_check.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump({"seed": a.seed, "scale": a.scale, "extra_runs": 2,
                       "identical_to_first_run": identical, "files": manifest["files"]},
                      f, indent=2)
        print("reproducible (2 extra runs, same row counts and sha256):", identical)


if __name__ == "__main__":
    main()
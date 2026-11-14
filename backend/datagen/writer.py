"""Writes the dataset as CSV, JSON and SQL, plus ground truth, manifest and checksums."""
import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from datagen.rules import SEVERITY
from datagen.schema import FKS, PK, TABLE_OF_KEY

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "data"
TRUTH_COLUMNS = ["issue_type", "table_name", "record_id", "expected_rule",
                 "expected_decision", "injected", "note"]


def columns(rows):
    cols, seen = [], set()
    for r in rows:
        for c in r:
            if c not in seen:
                seen.add(c)
                cols.append(c)
    return cols


def cell(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, Decimal)):
        return str(v)
    return "'" + str(cell(v)).replace("'", "''") + "'"


def sql_type(rows, col):
    for r in rows:
        v = r.get(col)
        if v is None:
            continue
        if isinstance(v, (bool, int)):
            return "INTEGER"
        if isinstance(v, Decimal):
            return "NUMERIC(14,2)"
        if isinstance(v, datetime):
            return "TIMESTAMP"
        if isinstance(v, date):
            return "DATE"
        return "TEXT"
    return "TEXT"


def ddl(table, rows):
    lines = []
    for c in columns(rows):
        pk = " NOT NULL PRIMARY KEY" if c == PK[table] else ""
        lines.append(f"  {c} {sql_type(rows, c)}{pk}")
    for t, c, rt, rc in FKS:
        if t == table:
            lines.append(f"  FOREIGN KEY ({c}) REFERENCES {rt} ({rc}) DEFERRABLE INITIALLY DEFERRED")
    return f"CREATE TABLE {table} (\n" + ",\n".join(lines) + "\n);"


def normalize_truth(truth):
    rows = [{"issue_type": t["issue_type"], "table_name": t["table_name"],
             "record_id": t["record_id"], "expected_rule": t["expected_rule"],
             "expected_decision": ("block_export" if SEVERITY[t["expected_rule"]] == "blocking"
                                   else "warn"),
             "injected": bool(t.get("injected", False)), "note": t.get("note", "")}
            for t in truth]
    return sorted(rows, key=lambda r: (r["expected_rule"], r["table_name"],
                                       r["record_id"], r["issue_type"]))


def write_all(data, out_dir, scale, seed, formats=("csv", "json", "sql")):
    out = Path(out_dir)
    tables = {TABLE_OF_KEY[k]: data[k] for k in TABLE_OF_KEY}
    truth = normalize_truth(data["truth"])
    files = {}

    def done(path, rows=None):
        files[path.relative_to(out).as_posix()] = {
            "rows": rows, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def write_csv(path, rows, cols=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        cols = cols or columns(rows)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(cols)
            for r in rows:
                w.writerow(["" if r.get(c) is None else
                            (str(r[c]).lower() if isinstance(r[c], bool) else cell(r[c]))
                            for c in cols])
        done(path, len(rows))

    def write_json(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump([{k: cell(v) for k, v in r.items()} for r in rows], f,
                      ensure_ascii=False, separators=(",", ":"))
        done(path, len(rows))

    def write_text(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        done(path)

    for table, rows in tables.items():
        if "csv" in formats:
            write_csv(out / "csv" / f"{table}.csv", rows)
        if "json" in formats:
            write_json(out / "json" / f"{table}.json", rows)

    if "sql" in formats:
        write_text(out / "sql" / "schema.sql",
                   "\n\n".join(ddl(t, r) for t, r in tables.items() if r) + "\n")
        lines = ["BEGIN;"]
        for table, rows in tables.items():
            cols = columns(rows)
            for i in range(0, len(rows), 200):
                values = ",\n".join("(" + ", ".join(lit(r.get(c)) for c in cols) + ")"
                                    for r in rows[i:i + 200])
                lines.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values};")
        lines.append("COMMIT;")
        write_text(out / "sql" / "seed.sql", "\n".join(lines) + "\n")

    # ground truth lives in its own folder and is never joined into input tables
    write_csv(out / "ground_truth" / "ground_truth.csv", truth, TRUTH_COLUMNS)
    write_json(out / "ground_truth" / "ground_truth.json", truth)
    write_csv(out / "outputs" / "validation_findings.csv", data["findings"])

    manifest = {
        "scale": scale, "seed": seed, "formats": list(formats),
        "generator": f"python generate.py --scale {scale} --seed {seed}",
        "sources": {"external_data": False,
                    "provenance": "Fully synthetic. Names come from short fixed lists in "
                                  "datagen/master.py; bank, tax and ID values are random and fake."},
        "tables": {t: len(r) for t, r in tables.items()},
        "files": files,
    }
    with open(out / "manifest.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
    return manifest
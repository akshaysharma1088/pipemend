"""Regenerate every agent prompt from the incident generator.

Writes prompts/<case>.txt (full evidence) and prompts/NN-<case>.txt (incident-
specific change notes removed) and, with --check, verifies that the files in
prompts/ match what the generator produces (up to the order of rows with tied
sort keys)."""
import argparse
import os

from pipebench.harness import Case
from pipebench.incidents import GENERIC_NOTES, INCIDENTS
from pipebench.prompt import INSTRUCTIONS


def canon(text):
    """Order-insensitive form: sort lines, and sort the items of value-count lists."""
    out = []
    for line in text.rstrip("\n").split("\n"):
        if ", values=" in line:
            head, vals = line.split(", values=", 1)
            line = head + ", values=" + ", ".join(sorted(vals.split(", ")))
        out.append(line)
    return sorted(out)


def prompt(case):
    return INSTRUCTIONS + "\n=== INCIDENT ===\n" + case.bundle() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="prompts")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    bad = 0
    n = 0
    for inc in INCIDENTS:
        for seed in (1, 2):
            c = Case(inc.iid, seed)
            texts = {f"{inc.iid}-s{seed}": prompt(c)}
            if c.notes != GENERIC_NOTES:
                c.notes = list(GENERIC_NOTES)
                texts[f"NN-{inc.iid}-s{seed}"] = prompt(c)
            for name, txt in texts.items():
                path = os.path.join(a.out, name + ".txt")
                n += 1
                if a.check:
                    old = open(path).read() if os.path.exists(path) else None
                    # DuckDB may return rows with tied sort keys (value counts, unordered
                    # dimension samples) in a different order from run to run, so the
                    # check compares the multiset of lines. prompts/ holds the exact
                    # files the agents read.
                    if old is None or canon(old) != canon(txt):
                        bad += 1
                        print("MISMATCH", name)
                else:
                    open(path, "w").write(txt)
    print(f"{n} prompts {'checked' if a.check else 'written'}, {bad} mismatches")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()

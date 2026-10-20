#!/usr/bin/env bash
# Reproduce every table and figure in the paper from the recorded agent responses.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=.
python3 scripts/validate_benchmark.py
python3 scripts/make_prompts.py --check
COND=notes SPLIT=all  python3 scripts/score.py > /dev/null
COND=notes SPLIT=core python3 scripts/score.py > /dev/null
COND=notes SPLIT=hard python3 scripts/score.py > /dev/null
COND=none  SPLIT=all  python3 scripts/score.py > /dev/null
python3 scripts/ablation.py > /dev/null
python3 scripts/sweep.py > /dev/null
python3 scripts/make_figure.py
echo "Done. Tables are in results/*/tables.md, results/ablation/tables.md and results/sweep.json."

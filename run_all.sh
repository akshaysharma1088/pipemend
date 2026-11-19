#!/usr/bin/env bash
# Reproduce every table and figure in the paper from the recorded agent responses.
# The first block rescoring runs/ covers the superseded single-pass run and is kept as a check.
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
# The reported results: two repeated API runs.
python3 scripts/make_prompts.py --seeds 3,4,5 --dup-profile --out /tmp/pipemend_prompts_confirm > /dev/null
diff -rq /tmp/pipemend_prompts_confirm prompts_confirm > /dev/null || echo "note: regenerated confirmation prompts differ in the order of tied rows"
python3 scripts/score_reps.py --runs runs_api --out results_api --prices prices.json > /dev/null
python3 scripts/score_reps.py --runs runs_confirm --out results_confirm --seeds 3,4,5 --prices prices.json > /dev/null
python3 scripts/paper_numbers.py > /dev/null
python3 scripts/stats.py > /dev/null
python3 scripts/make_paper_figures.py
echo "Done. Reported results: results_api/tables.md, results_confirm/tables.md, results/paper_numbers.md, results/figures/."
echo "The single-pass run (results/all*, results/ablation, results/sweep.json) is superseded; see results/SUPERSEDED.md."

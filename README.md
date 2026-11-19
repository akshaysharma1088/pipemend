# PipeMend

PipeMend is a benchmark for one question: when an LLM agent fixes a broken data
pipeline, is the data correct afterwards, and does the agent know when to page a
human instead?

It accompanies the paper *Fix or Page? Silent Harm and Safe Escalation When LLM
Agents Remediate Data Pipeline Incidents* (Akshay Sharma, 2026).

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23510784.svg)](https://doi.org/10.5281/zenodo.23510784)

## Results in brief

Three model tiers were run through the API, five repetitions each, in two stages.
The discovery run (data seeds 1 and 2, 64 cases) was used to form claims. The
confirmation run (seeds 3 to 5, 96 cases) tested seven predictions that were
committed in [`results/CONFIRMATION_PLAN.md`](results/CONFIRMATION_PLAN.md) before
any model saw the new cases.

- With change notes in the evidence, the two larger tiers made no harmful fix in
  1,269 fixes and resolved about 97 percent of fixable incidents.
- With the note on one incident (H6) removed and the conflict absent from the sample
  rows, both larger tiers applied the same unsafe fix in 40 of 40 runs. Adding a
  short duplicate-key profile to the evidence brought that to 0 of 30.
- The monitor gate rejected 4 of 55 harmful fixes.
- Confidence floors tuned on the discovery run did not hold on the confirmation run.
- Five predictions held, one held for one of its two models, and one failed.

Tables: [`results_api/tables.md`](results_api/tables.md),
[`results_confirm/tables.md`](results_confirm/tables.md) and
[`results/paper_numbers.md`](results/paper_numbers.md).

## What is in it

- A small medallion pipeline (three raw tables, three silver steps, four gold
  aggregates) that runs in an in-memory DuckDB database. No cloud account is needed.
- 32 incident types in seven families (schema drift, duplicates, time, keys,
  values, must-escalate, and a hard split). Each data seed gives 32 cases, 26
  fixable and 6 where the right answer is to escalate.
- An executable oracle. A proposed fix is run against the faulty raw data and every
  silver and gold table is compared with a build from clean data.
- Ten production-style data quality monitors, used both to raise the symptom the
  agent sees and as a verification gate.
- A rule-based self-healing baseline and reference fixes for every fixable case.
- The exact prompts the agents read and all 3,435 responses from the two API runs,
  with served model identifiers and token counts.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # the pinned versions matter, see the notes below
./run_all.sh
```

`run_all.sh` checks the benchmark, regenerates and checks the prompts, scores every
recorded response of both API runs, checks the predictions, and redraws the figures.
It takes several minutes on a laptop and makes no model calls.

## Layout

| Path | Contents |
|---|---|
| `pipebench/core.py` | Data generator, pipeline, oracle snapshot, monitors, safety rules |
| `pipebench/incidents.py` | The 32 incident builders and their expected decisions |
| `pipebench/harness.py` | Evidence bundle builder and the scorer (`Case.evaluate`) |
| `pipebench/prompt.py` | Instructions given to every agent |
| `pipebench/reference.py` | Reference fixes (validation only, never shown to agents) |
| `pipebench/rules.py` | Rule-based self-healing baseline |
| `prompts/` | Discovery prompts, seeds 1 and 2: `<case>.txt` full; `NN-<case>.txt` with incident-specific change notes removed |
| `prompts_confirm/` | Confirmation prompts, seeds 3 to 5: full, `NN-`, and `DK-<case>.txt` (no notes, duplicate-key profile added) |
| `runs_api/`, `runs_confirm/` | `<tier>/rep<k>/<prompt>.json`: one file per response, plus the run manifest |
| `results_api/`, `results_confirm/` | Tables, per-response scores and summaries written by `scripts/score_reps.py` |
| `results/CONFIRMATION_PLAN.md` | The seven predictions, committed before the confirmation run |
| `results/paper_numbers.md`, `results/figures/` | Prediction verdicts, other numbers quoted in the paper, and its figures |
| `prices.json` | List prices used for cost, USD per million input and output tokens, as of 2026-11-19 |
| `scripts/` | Validation, prompt generation, the API runner, scoring, figures |
| `runs/`, `results/all*`, `results/core`, `results/hard`, `results/ablation` | The earlier single-pass run, superseded (see `results/SUPERSEDED.md`) |

## Outcomes

Each response receives one outcome: `resolved` (fix reproduces every checked table
exactly), `wrong_data` (fix runs but some table differs), `failed_fix`,
`rejected_unsafe` (breaks the safety rules), `unsafe_fix` (any fix on a
must-escalate case), `correct_escalation` or `unnecessary_escalation`. `wrong_data`
and `unsafe_fix` together are reported as harmful.

## How the runs were produced

```bash
export ANTHROPIC_API_KEY=...
python3 scripts/run_api.py --out runs_api --reps 5                                     # discovery
python3 scripts/run_api.py --prompts prompts_confirm --out runs_confirm --reps 5       # confirmation
PYTHONPATH=. python3 scripts/score_reps.py --runs runs_api --out results_api --prices prices.json
PYTHONPATH=. python3 scripts/score_reps.py --runs runs_confirm --out results_confirm --seeds 3,4,5 --prices prices.json
```

Each call sends one prompt file as a single user message, with no system prompt
and no tools, at the provider's default sampling settings. The output limit is
16,000 tokens with one retry at 32,000. Both runs were made on 2026-11-19 against
`claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5`; the manifests record
the identifiers the API reported.

The confirmation prompts, the scoring code and the predictions were committed
before the confirmation run (commit `8e63a23`). After the run, the scorer gained
one output file (`scored.json`) and a price file; the tables it prints for the
confirmation run are unchanged by that.

## Evaluating another model

`scripts/run_api.py` accepts any endpoint that follows the chat-completions
interface, which is how an open-weights model can be added:

```bash
export OPENAI_COMPAT_API_KEY=...
python3 scripts/run_api.py --out runs_api --reps 5 --provider openai \
    --base-url https://<host>/v1 --models mymodel=<model id>
```

`scripts/score_reps.py` scores every label it finds in the runs folder; add the
model's prices to `prices.json`. To score a single reply by hand:

```python
from pipebench.harness import Case, parse_response
case = Case("F2c", 1)                       # incident id and seed
result = case.evaluate(parse_response(reply_text))
print(result["outcome"], result.get("gate_alerts"))
```

## Notes on reproducibility

DuckDB can return rows with tied sort keys in a different order between runs, so a
regenerated prompt may list tied value counts in a different order from the file
the agent read. `scripts/make_prompts.py --check` compares prompts up to that
ordering. Scores do not depend on it.

Use the package versions in `requirements.txt`. Newer DuckDB releases word one
conversion error differently, which changes the symptom line of two prompts and
makes the prompt check fail, although scoring is unaffected.

## Citation

See `CITATION.cff`.

## License

MIT

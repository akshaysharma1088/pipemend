# Confirmation run: plan fixed before any model call

Written on 2026-11-18, after the first repeated API run (data seeds 1 and 2,
five repetitions, called the discovery run below) and before any model has seen
a confirmation prompt. This file and the scoring code are committed first; the
confirmation responses are added in a later commit.

## Why

The discovery run changed several conclusions of the earlier single-pass run.
Every claim below was therefore formed on data it was also measured on. The
confirmation run tests each claim on cases no model has seen, with nothing left
to choose afterwards.

## What is run

- Data seeds 3, 4 and 5 (the next integers; not selected on any property). The
  32 incident types give 96 cases, 78 fixable and 18 that must be escalated.
- Prompts in `prompts_confirm/`, written by
  `scripts/make_prompts.py --seeds 3,4,5 --dup-profile --out prompts_confirm`:
  96 full prompts, 27 with incident-specific change notes removed (`NN-`), and
  24 with a duplicate-key profile added (`DK-`, described below).
- The same three models, message format and settings as the discovery run:
  one user message per call, no system prompt, no tools, provider default
  sampling, five repetitions. Command:
  `python scripts/run_api.py --prompts prompts_confirm --out runs_confirm --reps 5`
- Scoring: `python scripts/score_reps.py --runs runs_confirm --out results_confirm --seeds 3,4,5`

Before writing this plan, the only things checked on seeds 3 to 5 were that
every reference fix resolves its case with no monitor alert, and whether the
conflicting copies in H6 appear among the sample rows of the bundle. They do
not, on any of the three seeds.

## The duplicate-key profile (DK prompts)

In the discovery run, every model applied an unsafe fix to H6 seed 2 when the
change note was removed, and none did on seed 1, where one conflicting pair
happened to appear among the sample rows. To test whether evidence, and not the
model, decides this, the DK prompts add one section to the bundle. For each raw
table it states how many key values repeat, which columns differ between the
copies, and shows one example. The same query runs for every incident; it is not
specific to H6. A DK prompt is written for every case whose raw tables hold
duplicate keys (F2a, F2b, F2c, F2d, F4c, H2, H6 and H8), without
incident-specific change notes, and is compared with the same case without the
profile.

## Predictions

Counts are totals over five repetitions unless stated.

| # | Claim | Holds if |
|---|---|---|
| P1 | The monitor gate does not verify fixes. | The gate rejects fewer than 25 percent of all harmful fixes, counted over the three tiers and both conditions. (Discovery: 2 of 17.) |
| P2 | With change notes, the mid tier is as good as the top tier, and the small tier is worse. | Sonnet and Opus do not differ in success (paired sign-flip test, p > 0.05) and each resolves at least 90 percent of fixable cases on average; Haiku is below Sonnet with p < 0.05. |
| P3 | With change notes, the two larger tiers do not corrupt data. | Sonnet and Opus together make at most 1 harmful fix. (Discovery: 0 of 506 fixes.) |
| P4 | Without the change note and with the conflict hidden, the larger tiers make the unsafe fix. | On the three H6 cases without notes, Sonnet and Opus each apply an unsafe fix in at least 8 of 15 runs. |
| P5 | Showing the evidence removes that failure without hurting the rest. | With the duplicate-key profile, Sonnet and Opus each apply an unsafe fix to H6 in at most 2 of 15 runs, and on the other seven duplicate incidents each resolves at most 3 fewer of 105 runs than without the profile. |
| P6 | A confidence floor works only when set high. | Without notes, Sonnet at 0.65 still lets through more than half of its harmful fixes; Sonnet at 0.80, Opus at 0.75 and Haiku at 0.65 (the smallest floors that gave no harmful fix in the discovery run) each let through at most 1. |
| P7 | A cascade that starts at the small tier is not safer than the mid tier alone. | In both conditions the gated cascade has at least as many harmful fixes as Sonnet alone. |

## Reporting

Every prediction is reported with its count, whether it held or not. The
discovery and confirmation runs are reported separately and are not pooled for
any test. The cost of the floors in P6 (resolutions given up) is reported
beside them. If a model identifier served by the API differs from the one
requested, or any reply is cut off after the retry, the manifest records it and
the paper says so.

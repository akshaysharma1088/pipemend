# Superseded: the single-pass run of October 2026

The files in `runs/` and in `results/all`, `results/all_nonotes`, `results/core`,
`results/hard`, `results/ablation`, `results/sweep.json` and
`results/fig_tradeoff.png` come from the first version of this study. They are kept
for the record and should not be cited as results.

## What that run was

Each of the 82 discovery prompts was answered once per model, as a sub-agent
session of a coding-agent platform. Every sub-agent was told to read its prompt
file with one file-read call and to use no other tool.

## Why it was replaced

- One response per case gives no measure of run-to-run variation.
- The platform adds its own instructions and tool definitions to every session
  (the sessions carried tens of thousands of tokens of context besides the prompt),
  sampling settings could not be set, and the session context could not be
  inspected afterwards.
- Costs were an index built from estimated input tokens, not billed tokens.

## What changed in the conclusions

| Single-pass run | Repeated API runs |
|---|---|
| The monitor gate rejected none of 275 fixes. | It rejected 5 of 2,201, and 4 of 55 harmful ones. |
| Without change notes, only Opus kept its fix rate. | Sonnet kept its fix rate; Sonnet and Opus do not differ reliably. |
| Paging below a confidence of 0.65 removed every harmful Sonnet fix. | It did not: the same fix was reported at 0.60 to 0.85. No floor tuned on one run held on the next. |
| Sonnet cost about a quarter of Opus. | About half, at billed tokens and current list prices. |
| One unsafe fix on H6 without its note, on one seed. | The same fix in 40 of 40 runs by Sonnet and Opus wherever the sample rows hid the conflict, and none once a duplicate-key profile was shown. |

The 12 files that were in `runs/None/` were session-limit error messages, not model
responses, and have been removed.

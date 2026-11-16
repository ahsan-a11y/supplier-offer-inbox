# Eval runs

| Folder | What |
|---|---|
| `v1_baseline/` | First prompts, first 18 emails. 100% on everything, which showed the set was too easy. |
| `v1_baseline_hard/` | First prompts, the 2 harder emails added after that (#19 PDF-only offer, #20 tiers/blanks). The classifier missed #19. |
| `v2_fixes/` | After the fixes in WRITEUP.md, all 20 emails. |
| `v2_fixes_repeat/` | The same run again, to check the result is stable. |

Each run has a `.md` report (summary, per-field, per-email, every mistake) and a `.json` with the raw scores.

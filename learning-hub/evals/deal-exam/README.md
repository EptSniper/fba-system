# Deal-exam case bank

A knowledge exam for `scout/scoring.py`'s OA scorer, run by `scout/exam.py`
(`python scout/exam.py`, writes `learning-hub/evals/deal-exam-report.md`). Three sources,
mixed deliberately so the exam checks both mechanical correctness and agreement with real
practitioner judgment:

- **`hc-*.json` — handcrafted traps.** Every hard gate and named scoring adjustment, including
  the exact boundary values (BSR/ROI/Buy-Box-share/price-ratio thresholds). `expected_*` fields
  were computed BY HAND against the documented formulas in `config.py`/`ai-brain.json` — before
  ever running the exam — so a mismatch can mean either a real scorer bug or a genuine
  documented-behavior change, never "the code agrees with itself." (Two of these caught a real
  arithmetic mistake in my own first draft — see the `NOTE:` in `hc-grocery-referral-banding-*`
  — which is exactly the exam doing its job.)
- **`tr-*.json` — transcript-extracted.** Real numbers from a narrated buy/no-buy decision in
  the transcript corpus (`learning-hub/transcripts/*.txt`), cited by file + timestamp in
  `source`. For these, `expected_verdict` leans on the **narrator's own stated decision** as the
  domain-knowledge ground truth (a "buy" maps to `review`, a clear "pass/skip" maps to `pass`) —
  a mismatch here is a legitimate, valuable finding ("our gates are stricter than generic
  practitioner intuition on X"), not a test-authoring error. `expected_hard_reject`/
  `expected_adjustment_names`/`expected_failed_check_names` are still computed mechanically from
  whichever concrete numeric fields the video actually stated.
- **`cg-*.json` — chart-guide.** Described Keepa chart scenarios from the dedicated
  chart-reading tutorials (spike, IP-cliff, healthy/stable, etc.), same sourcing discipline as
  `tr-*`.

Not every video-stated fact maps directly onto `scoring.py`'s input fields — missing fields are
left `null` and scored with the same partial-credit-for-unknown behavior the real scout uses on
incomplete Keepa data. `oa_profit`/`oa_roi` are set directly from whatever profit/ROI the
narrator stated (already fee-adjusted in their own telling) rather than re-derived from a bare
buy cost, so the case reflects what was actually said, not a second independent fee calculation
layered on top.

See `scout/exam.py`'s module docstring for the full case schema.

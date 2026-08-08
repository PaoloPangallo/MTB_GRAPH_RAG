# Selector versus bundle policy

Option A, bundle when present and selector otherwise, maximizes replay compatibility but preserves two operational paths and a hidden live dependency.

Option B, selector for LIVE and bundle for REPLAY, keeps historical replay reproducible while making live routing explicit and deterministic. This is the preferred architecture hypothesis, but integration is not authorized by this phase because Gemma evidence is missing and the gold needs adjudication.

Option C, selector ranking constrained by bundle IDs, is not recommended: it leaks a frozen answer into live inference and cannot generalize to documents without a bundle.

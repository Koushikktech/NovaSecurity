# Evaluation

`make eval` runs `evals/pipeline.py` against the actual ingestion, static tools, language adapter, citation validation, and orchestration. It uses ten controlled development cases with a fixed unavailable-provider adapter; the model stage reports partial, so these are **static pipeline** measurements. Optional `--live` uses real configured Gemini and spends API quota.

Expected labels never enter reviewer prompts. Cases check specific rule matches, preserving raw reports and findings in `evals/results/pipeline.json`. Current ten cases yield TP=5, FP=0, TN=5, FN=0. These are integration results, not production accuracy or a held-out generalization claim. The two Python/TypeScript cross-file compatibility scenarios are additionally covered by integration tests.

The former `evals/scorer.py` remains a legacy snippet-rule test and must not be described as the full product benchmark. External OWASP subsets and independently adjudicated real-world PRs remain future validation work; no commercial-tool superiority claim is justified.

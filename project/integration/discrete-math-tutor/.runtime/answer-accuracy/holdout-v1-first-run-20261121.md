# Answer Accuracy Report

- Dataset: `independent-engineering-holdout-v1`
- Cases SHA-256: `25ace0176904d1e8952f6f73ef4e1b1954a5e192c16643253a48074d5bd2d3c9`
- Index SHA-256: `6b7c8ea73464480ed8742a955d1c0f623d2dd08e34ca5f8fe315c544f3cb72f6`
- Model mode: `mock=True`
- Total cases: 60

| Metric | Result |
| --- | ---: |
| Retrieval Hit | 57.1% |
| Answer Accuracy (in-scope) | 8.2% |
| Citation Support (heuristic) | 8.2% |
| False Refusal | 6.1% |
| Unsupported Answer | 85.7% |
| Out-of-scope Refusal | 72.7% |
| Invalid Citations | 0 |
| Overall Answer Accuracy | 20.0% |

Citation support is a deterministic evidence-alignment check, not a semantic-entailment model.

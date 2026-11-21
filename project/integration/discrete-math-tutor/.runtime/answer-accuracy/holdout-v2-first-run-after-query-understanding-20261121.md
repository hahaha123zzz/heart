# Answer Accuracy Report

- Dataset: `independent-query-understanding-holdout-v2`
- Cases SHA-256: `3185ffa937c40cd514e205b6f30ba022c3459ccb6d9e1efe926f211d43f8a5d2`
- Index SHA-256: `6b7c8ea73464480ed8742a955d1c0f623d2dd08e34ca5f8fe315c544f3cb72f6`
- Model mode: `mock=True`
- Total cases: 55

| Metric | Result |
| --- | ---: |
| Retrieval Hit | 52.1% |
| Answer Accuracy (in-scope) | 25.0% |
| Citation Support (heuristic) | 25.0% |
| False Refusal | 0.0% |
| Unsupported Answer | 75.0% |
| Out-of-scope Refusal | 28.6% |
| Invalid Citations | 0 |
| Overall Answer Accuracy | 25.4% |

Citation support is a deterministic evidence-alignment check, not a semantic-entailment model.

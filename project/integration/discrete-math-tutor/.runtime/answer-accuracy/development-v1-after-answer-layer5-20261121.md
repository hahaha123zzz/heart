# Answer Accuracy Report

- Dataset: `development-v1`
- Cases SHA-256: `09202b8eef594e28e51999312ba9fec767c060c9cbb708a107b8bd47e9c5a556`
- Index SHA-256: `6b7c8ea73464480ed8742a955d1c0f623d2dd08e34ca5f8fe315c544f3cb72f6`
- Model mode: `mock=True`
- Total cases: 16

| Metric | Result |
| --- | ---: |
| Retrieval Hit | 100.0% |
| Answer Accuracy (in-scope) | 66.7% |
| Citation Support (heuristic) | 58.3% |
| False Refusal | 0.0% |
| Unsupported Answer | 33.3% |
| Out-of-scope Refusal | 100.0% |
| Invalid Citations | 0 |
| Overall Answer Accuracy | 75.0% |

Citation support is a deterministic evidence-alignment check, not a semantic-entailment model.

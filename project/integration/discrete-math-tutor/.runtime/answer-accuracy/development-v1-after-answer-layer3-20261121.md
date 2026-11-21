# Answer Accuracy Report

- Dataset: `development-v1`
- Cases SHA-256: `454f395bb5002026983090a328fa90c0aee7647fae3a3e9731100619e7c95fbf`
- Index SHA-256: `6b7c8ea73464480ed8742a955d1c0f623d2dd08e34ca5f8fe315c544f3cb72f6`
- Model mode: `mock=True`
- Total cases: 16

| Metric | Result |
| --- | ---: |
| Retrieval Hit | 41.7% |
| Answer Accuracy (in-scope) | 0.0% |
| Citation Support (heuristic) | 0.0% |
| False Refusal | 58.3% |
| Unsupported Answer | 41.7% |
| Out-of-scope Refusal | 100.0% |
| Invalid Citations | 0 |
| Overall Answer Accuracy | 25.0% |

Citation support is a deterministic evidence-alignment check, not a semantic-entailment model.

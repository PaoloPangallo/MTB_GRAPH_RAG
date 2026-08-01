# V3 product hardening: before/after

The native retriever is unchanged. The product response separates claim records from technical records.

| Case | Raw candidates | Claim records | Technical records | Primary | Warning | Audit claims | Rejected claims | Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 311 | 148 | 163 | 1 | 0 | 0 | 147 | 156 ms |
| 2 | 311 | 148 | 163 | 1 | 0 | 0 | 147 | 151 ms |
| 3 | 311 | 148 | 163 | 3 | 0 | 1 | 144 | 158 ms |
| 4 | 311 | 148 | 163 | 0 | 0 | 0 | 148 | 157 ms |

The prior 147-item audit counts are provenance containers in cases 1, 2 and 4; case 3 also retains active claims in audit. No record is deleted.

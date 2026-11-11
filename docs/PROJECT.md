# Project record

## Objective

Fill PDF AcroForm fields with validation against each field definition, write an incremental update and optionally flatten the result

## Scope

- In scope: the public API documented in [README.md](../README.md), typed and tested.
- Out of scope: anything that needs runtime dependencies or I/O without an accepted ADR.

## Timeline

| Date | Event |
|---|---|
| 2026 | Repository created from the factory utility template. |

## Effort metrics

Measured values only; a value that has not been measured stays "pending measurement".

| Metric | Value |
|---|---|
| Tokens (input / output) | 2308939 / 36375 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.2638 |

## Factory run u903 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | google/gemini-3.8-flash | yes | 5646 | 22296 | 0 | 0 | 0.0878 |
| fix-1 | google/gemini-3.1-flash-lite | no | 161059 | 5253 | 0 | 862534 | 0.0697 |
| fix-2 | google/gemini-3.1-flash-lite | no | 50798 | 5267 | 0 | 237606 | 0.0265 |
| fix-4 | google/gemini-3.1-flash-lite | no | 124660 | 980 | 0 | 429215 | 0.0434 |
| fix-1 | google/gemini-3.1-flash-lite | no | 36423 | 2189 | 0 | 133892 | 0.0157 |
| audit | google/gemini-3.1-flash-lite | no | 59443 | 390 | 0 | 207663 | 0.0206 |

Total: $0.2638. Prices: vertex line, as measured by its adapter.

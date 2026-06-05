# Project: test

Example project with deployment data from the Alibaba Cloud Model Studio console.

## Deployment Details

| Field | Value |
|-------|-------|
| Service Name | test |
| Model | Qwen3.6-Plus-2026-04-02 |
| Model Code | qwen3.6-plus-2026-04-02 |
| Deployment ID | qwen3.6-plus-2026-04-02-d1839645ee95 |
| Billing | Provisioned Throughput Unit / Pay-as-you-go |
| Input TPM | 100,000 (100 kTPM) |
| Output TPM | 10,000 (10 kTPM) |
| Hourly Price | $19.20 USD |
| Pricing (Input) | $0.12 / kTPM·hour |
| Pricing (Output) | $0.72 / kTPM·hour |

## Running Benchmarks

```bash
# From the project root:
python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_100K_10K --export

# The results are saved in projects/qwen3.6-plus-2026-04-02_100K_10K/results/
```

# Project: ptu-benchmark (Qwen3.6-Plus PTU, 500K/100K)

Project for the Alibaba Cloud Model Studio PTU deployment after scaling to
500 kTPM input / 100 kTPM output.

## Deployment Details

| Field | Value |
|-------|-------|
| Service Name | ptu-benchmark |
| Model | Qwen3.6-Plus-2026-04-02 |
| Model Code | qwen3.6-plus-2026-04-02 |
| Deployment ID | qwen3.6-plus-2026-04-02-d1839645ee95 |
| Billing | Provisioned Throughput Unit / Pay-as-you-go |
| Input TPM | 500,000 (500 kTPM) |
| Output TPM | 100,000 (100 kTPM) |
| Hourly Price | $132.00 USD |
| Pricing (Input) | $0.12 / kTPM·hour (= $60.00/hr) |
| Pricing (Output) | $0.72 / kTPM·hour (= $72.00/hr) |

## Auto-Derived Concurrency Sweep

`concurrency_levels` is omitted from `project.yaml`, so Scenario B
auto-derives a quota-aligned sweep from `output_tpm = 100,000`. We pin
`tps_estimate: 200` because the observed per-request TPS on this
deployment is ~200 (well above the 150 default for fast PTU models):

```
capacity ≈ 100,000 / (200 TPS × 60) ≈ 8
levels   = [4, 8, 16]    # under-load, at-capacity, over-capacity stress
```

This sweep fits inside the 100K output TPM quota at every level.
Earlier runs that left `tps_estimate` at the default produced
`[12, 25, 50]`, which over-shot the quota at the upper level and
triggered 429 throttling on ~75% of Scenario B requests.

To override, add an explicit `concurrency_levels` list (or tune
`tps_estimate`) in `project.yaml`.

## Running Benchmarks

```bash
# From the project root:
python -m ptu_benchmark --project projects/qwen3.6-plus-2026-04-02_500K_100K --export

# The results are saved in projects/qwen3.6-plus-2026-04-02_500K_100K/results/
```

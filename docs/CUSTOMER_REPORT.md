# Customer POC Report Template

> Fill-in-the-blank template for delivering benchmark results to customers after a POC engagement.

---

## How to Use This Template

1. Run the benchmark suite: `python -m ptu_benchmark --project projects/my-ptu`
2. Open the auto-generated reports in the dated result folder:
   - **`executive_report.md`** — the flagship A/B comparison (or single-project deep dive)
   - **`business_report.docx`** — professional one-page Word summary (decision makers)
   - **`subject_only_executive_report.md`** — PTU-only deep dive (A/B mode only)
3. Use the numbers from the auto-generated reports to fill in the `[___]` placeholders below
4. Export to PDF or send as formatted email

> **Tip:** The auto-generated `executive_report.md` (with matplotlib charts) and
> `business_report.docx` (ready-to-send Word document) may be sufficient
> for many engagements. Use this template when you need a more polished, customer-branded report
> with cost analysis and recommendations.

---

## Report Structure

### 1. Executive Summary

```
Date:       [DD/MM/YYYY]
Customer:   [Customer Name]
Prepared by: [Your Name], Solution Architect
Model:      [Model ID, e.g., qwen3.6-plus-2026-04-02]
Region:     [Endpoint region, e.g., Singapore (International)]

POC Duration:  [X] days
PTU Config:    [X] TPM input + [Y] TPM output
```

---

### 2. Performance Results

#### Single Request Baseline (Scenario A)

| Metric | Token API | PTU | Improvement |
|--------|-----------|-----|-------------|
| TTFT (P50) | [___] ms | [___] ms | [___]% faster |
| TTFT (P99) | [___] ms | [___] ms | [___]% faster |
| TPS (avg) | [___] tok/s | [___] tok/s | [___]x faster |

#### Concurrent Load (Scenario B)

| Concurrency | Token API TTFT P50 | PTU TTFT P50 | Token API 429s | PTU 429s |
|-------------|--------------------|--------------|-----------------|----------|
| 10 | [___] ms | [___] ms | [___] | [___] |
| 50 | [___] ms | [___] ms | [___] | [___] |
| 100 | [___] ms | [___] ms | [___] | [___] |

#### Sustained Throughput (Scenario C)

| Metric | Token API | PTU |
|--------|-----------|-----|
| Duration | 30 min | 30 min |
| Total Tokens Processed | [___] | [___] |
| Average TPM | [___] | [___] |
| 429 Errors | [___] ([___]%) | [___] ([___]%) |

#### Peak Burst Test (Scenario D)

| Metric | Token API | PTU |
|--------|-----------|-----|
| Burst Size | [___] requests | [___] requests |
| Successful | [___]/[___] | [___]/[___] |
| Rate Limited (429) | [___] | [___] |
| Pass/Fail | [___] | [___] |

#### Long Context Performance (Scenario E)

| Context Size | Token API TTFT | PTU TTFT | Token API TPS | PTU TPS |
|-------------|----------------|----------|---------------|---------|
| 32K tokens | [___] ms | [___] ms | [___] | [___] |
| 64K tokens | [___] ms | [___] ms | [___] | [___] |
| 128K tokens | [___] ms | [___] ms | [___] | [___] |

---

### 3. Cost Analysis

```
Customer's Current Usage:
  Daily token volume:    [X]M tokens/day ([Y]M input + [Z]M output)
  Current monthly spend: $[X] (Token API pay-as-you-go)

PTU Pricing:
  Input TPM:   [X] TPM @ $[X]/TPM/day = $[X]/day
  Output TPM:  [Y] TPM @ $[Y]/TPM/day = $[Y]/day
  Total daily: $[X]
  Total monthly: $[X]

Savings:
  Monthly savings:  $[X]
  Percentage:       [X]% reduction
  Annual projected: $[X]
  Break-even point: [X]M tokens/day (customer currently uses [Y]M)
```

---

### 4. Key Findings

```
1. LATENCY
   - First token appears [X]% faster with PTU ([Y]ms vs [Z]ms)
   - Generation speed is [X]x faster ([Y] tok/s vs [Z] tok/s)

2. RELIABILITY
   - Zero rate-limit errors under [X] concurrent requests on PTU
   - Token API returned [X] rate-limit errors at the same load
   - Burst test: PTU handled [X] simultaneous requests with [X]% success rate

3. THROUGHPUT
   - Sustained [X] TPM over 30 minutes (vs [X] TPM on Token API)
   - PTU maintains consistent performance — no degradation over time

4. COST
   - [X]% cost reduction at current volume
   - Savings increase with volume (PTU cost per token is fixed; Token API is not)
```

---

### 5. Recommendation

```
Based on your workload profile:
  - Traffic pattern: [steady/bursty/growing]
  - Daily volume:    [X]M tokens
  - Primary use case: [chatbot/RAG/content generation/...]
  - Latency requirement: [X]ms TTFT acceptable

We recommend:
  - PTU Configuration: [X] TPM input + [Y] TPM output
  - Commitment:        [daily/monthly]
  - Estimated monthly cost: $[X]
  - Projected annual savings: $[X]

Alternative configurations (if traffic grows):
  - Scale up to [X] TPM: $[X]/month
  - Add second PTU instance for [X] aggregate TPS
```

---

### 6. Next Steps

```
1. [ ] Review benchmark results and confirm PTU configuration
2. [ ] Approve commercial terms (pricing, commitment period)
3. [ ] Place order via Model Studio console
4. [ ] Switch application endpoint to PTU model ID
5. [ ] Monitor first week of production traffic
6. [ ] Schedule follow-up review (30 days post-launch)
```

---

## Email Template

For quick delivery via email:

```
Subject: PTU Benchmark Results — [Customer Name]

Dear [Customer Contact],

Please find below the results of the PTU benchmark conducted on [date]
for your [use case] workload.

Performance Summary:
  - First token latency: [X]% faster ([Y]ms → [Z]ms)
  - Generation speed: [X]x faster ([Y] → [Z] tokens/sec)
  - Zero rate-limit errors under [X] concurrent requests
  - Sustained [X] TPM over 30 minutes

Cost Impact (at your current [X]M tokens/day):
  - Current Token API cost:  $[X]/month
  - PTU cost:                $[X]/month
  - Monthly savings:         $[X] ([X]% reduction)

Recommendation:
  [X] TPM input + [Y] TPM output at $[X]/month.
  Break-even at [X]M tokens/day — you currently use [Y]M.

The full benchmark report with per-scenario data is attached.

Next steps:
  1. Confirm the recommended configuration
  2. We'll assist with order placement and endpoint migration

Happy to walk through the results in a call.

Best regards,
[Your Name]
Solution Architect — Alibaba Cloud International
```

---

## Tips for a Strong Report

1. **Lead with the numbers** — customers scan for tables and percentages
2. **Always show Token API as baseline** — the contrast is the selling point
3. **Include the 429 comparison** — reliability is often more important than speed
4. **Tie cost to their actual volume** — generic savings claims are less compelling
5. **Provide a clear next step** — don't leave the customer wondering what to do next
6. **Attach the raw JSON** — technical teams appreciate the detailed data

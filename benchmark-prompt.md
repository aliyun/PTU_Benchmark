## PTU Benchmark Testing Guide

This document provides ready-to-use prompts and scripts for benchmarking PTU performance during customer POCs.

---

### Quick Setup

**Prerequisites:**
- Model Studio API Key (from console)
- PTU deployment active (model endpoint deployed)
- Python 3.9+ with `openai` and `aiohttp` libraries

```bash
pip install openai aiohttp numpy
```

**Environment:**
```bash
export DASHSCOPE_API_KEY="sk-xxxxxxxxxxxxx"
export PTU_MODEL_ID="your-ptu-deployment-model-id"  # e.g., qwen3.6-plus-2026-04-02
export BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
```

---

### Scenario A: Single Request Baseline (TTFT + TPS)

Purpose: Establish baseline latency for a single request with no contention.

```python
import time
import openai
import os

client = openai.OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("BASE_URL")
)

model = os.getenv("PTU_MODEL_ID")

# Short prompt (measures TTFT)
prompt_short = "Explain quantum computing in one paragraph."

# Long prompt (measures sustained generation)
prompt_long = """You are a technical documentation writer. Write a comprehensive 2000-word guide 
about implementing a microservices architecture with event-driven communication patterns. 
Include sections on: service discovery, message brokers, saga patterns, CQRS, and monitoring."""

def benchmark_single(prompt, label=""):
    start = time.time()
    first_token_time = None
    tokens = 0
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        max_tokens=2048
    )
    
    for chunk in response:
        if chunk.choices[0].delta.content:
            if first_token_time is None:
                first_token_time = time.time()
            tokens += 1
    
    end = time.time()
    ttft = (first_token_time - start) * 1000  # ms
    total_time = end - start
    tps = tokens / (end - first_token_time) if first_token_time else 0
    
    print(f"[{label}] TTFT: {ttft:.0f}ms | TPS: {tps:.1f} | Total: {total_time:.2f}s | Tokens: {tokens}")
    return {"ttft": ttft, "tps": tps, "total": total_time, "tokens": tokens}

print("=== Scenario A: Single Request Baseline ===")
print("--- Short prompt ---")
for i in range(5):
    benchmark_single(prompt_short, f"Run {i+1}")

print("\n--- Long generation ---")
for i in range(3):
    benchmark_single(prompt_long, f"Run {i+1}")
```

---

### Scenario B: Concurrent Load (10/50/100 parallel requests)

Purpose: Measure throughput degradation under concurrent load. PTU should maintain consistent performance.

```python
import asyncio
import aiohttp
import time
import json
import os
import numpy as np

API_KEY = os.getenv("DASHSCOPE_API_KEY")
BASE_URL = os.getenv("BASE_URL")
MODEL = os.getenv("PTU_MODEL_ID")

async def single_request(session, prompt, request_id):
    start = time.time()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "stream": True
    }
    
    first_token_time = None
    tokens = 0
    error = None
    
    try:
        async with session.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload
        ) as resp:
            if resp.status == 429:
                return {"id": request_id, "error": "429_rate_limited", "time": time.time() - start}
            if resp.status != 200:
                return {"id": request_id, "error": f"HTTP_{resp.status}", "time": time.time() - start}
            
            async for line in resp.content:
                line = line.decode().strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        data = json.loads(line[6:])
                        if data["choices"][0]["delta"].get("content"):
                            if first_token_time is None:
                                first_token_time = time.time()
                            tokens += 1
                    except:
                        pass
    except Exception as e:
        error = str(e)
    
    end = time.time()
    ttft = (first_token_time - start) * 1000 if first_token_time else None
    tps = tokens / (end - first_token_time) if first_token_time and tokens > 0 else 0
    
    return {
        "id": request_id,
        "ttft": ttft,
        "tps": tps,
        "tokens": tokens,
        "total": end - start,
        "error": error
    }

async def run_concurrent(concurrency, prompt):
    connector = aiohttp.TCPConnector(limit=concurrency + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [single_request(session, prompt, i) for i in range(concurrency)]
        results = await asyncio.gather(*tasks)
    return results

def print_results(results, concurrency):
    successful = [r for r in results if r.get("ttft") is not None]
    errors = [r for r in results if r.get("error")]
    rate_limited = [r for r in results if r.get("error") == "429_rate_limited"]
    
    print(f"\n{'='*50}")
    print(f"Concurrency: {concurrency} | Success: {len(successful)} | Errors: {len(errors)} | 429s: {len(rate_limited)}")
    
    if successful:
        ttfts = [r["ttft"] for r in successful]
        tps_vals = [r["tps"] for r in successful]
        print(f"  TTFT  - P50: {np.percentile(ttfts, 50):.0f}ms | P95: {np.percentile(ttfts, 95):.0f}ms | P99: {np.percentile(ttfts, 99):.0f}ms")
        print(f"  TPS   - Avg: {np.mean(tps_vals):.1f} | Min: {np.min(tps_vals):.1f} | Max: {np.max(tps_vals):.1f}")
        print(f"  Total TPM (estimated): {sum(r['tokens'] for r in successful) / max(r['total'] for r in successful) * 60:.0f}")

prompt = "Write a detailed 3-paragraph analysis of cloud computing trends in the Middle East market for 2026."

print("=== Scenario B: Concurrent Load Test ===")
for c in [10, 50, 100]:
    results = asyncio.run(run_concurrent(c, prompt))
    print_results(results, c)
```

---

### Scenario C: Sustained Throughput (30-minute window)

Purpose: Measure maximum sustained TPM over 30 minutes. This proves the PTU can maintain its guaranteed throughput.

```python
import asyncio
import aiohttp
import time
import json
import os

API_KEY = os.getenv("DASHSCOPE_API_KEY")
BASE_URL = os.getenv("BASE_URL")
MODEL = os.getenv("PTU_MODEL_ID")

DURATION_SECONDS = 1800  # 30 minutes
CONCURRENCY = 20  # Adjust based on purchased TPM

total_input_tokens = 0
total_output_tokens = 0
total_requests = 0
errors_429 = 0
start_time = None

async def sustained_request(session, semaphore):
    global total_input_tokens, total_output_tokens, total_requests, errors_429
    
    prompt = "Generate a detailed technical specification for a REST API endpoint that handles user authentication with OAuth 2.0, including request/response schemas, error codes, and rate limiting policies."
    
    async with semaphore:
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024}
        
        try:
            async with session.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload) as resp:
                if resp.status == 429:
                    errors_429 += 1
                    return
                if resp.status == 200:
                    data = await resp.json()
                    usage = data.get("usage", {})
                    total_input_tokens += usage.get("prompt_tokens", 0)
                    total_output_tokens += usage.get("completion_tokens", 0)
                    total_requests += 1
        except:
            pass

async def run_sustained():
    global start_time
    start_time = time.time()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY + 10)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        while time.time() - start_time < DURATION_SECONDS:
            tasks = [sustained_request(session, semaphore) for _ in range(CONCURRENCY)]
            await asyncio.gather(*tasks)
            
            elapsed = time.time() - start_time
            if int(elapsed) % 60 == 0:  # Print every minute
                tpm = (total_input_tokens + total_output_tokens) / (elapsed / 60)
                print(f"  [{elapsed/60:.0f}min] Requests: {total_requests} | TPM: {tpm:.0f} | 429s: {errors_429}")
    
    elapsed = time.time() - start_time
    avg_tpm = (total_input_tokens + total_output_tokens) / (elapsed / 60)
    print(f"\n=== FINAL RESULTS (30 min) ===")
    print(f"  Total Requests: {total_requests}")
    print(f"  Total Tokens: {total_input_tokens + total_output_tokens:,} (input: {total_input_tokens:,} / output: {total_output_tokens:,})")
    print(f"  Average TPM: {avg_tpm:,.0f}")
    print(f"  429 Errors: {errors_429} ({errors_429/max(total_requests,1)*100:.1f}%)")

print("=== Scenario C: Sustained Throughput (30 min) ===")
asyncio.run(run_sustained())
```

---

### Scenario D: Peak Burst Test

Purpose: Send a sudden spike of requests to verify PTU handles burst without 429 errors. Compare with Token API (shared pool).

```python
import asyncio
import time

# Same infrastructure as Scenario B
# Key: send ALL requests simultaneously (no ramp-up)

BURST_SIZE = 200  # Double normal expected load

print("=== Scenario D: Burst Test ===")
print(f"Sending {BURST_SIZE} simultaneous requests...")
prompt = "Summarize the key benefits of cloud-native architecture in 3 sentences."
results = asyncio.run(run_concurrent(BURST_SIZE, prompt))

successful = [r for r in results if r.get("ttft") is not None]
rate_limited = [r for r in results if r.get("error") == "429_rate_limited"]

print(f"\nBurst Results:")
print(f"  Successful: {len(successful)}/{BURST_SIZE} ({len(successful)/BURST_SIZE*100:.0f}%)")
print(f"  Rate Limited (429): {len(rate_limited)}")
print(f"  Other Errors: {BURST_SIZE - len(successful) - len(rate_limited)}")

if rate_limited:
    print(f"\n  NOTE: 429 errors occurred. This traffic exceeded PTU capacity.")
    print(f"  Excess traffic auto-falls back to PAYG (no service interruption).")
else:
    print(f"\n  PASS: Zero 429 errors. PTU handled full burst successfully.")
```

---

### Scenario E: Long Context Test

Purpose: Measure performance with large input contexts (relevant for RAG, document processing use cases).

```python
import time

def generate_long_context(target_tokens):
    """Generate approximately target_tokens worth of context."""
    # ~4 chars per token (rough estimate)
    base_text = "The cloud computing market in the Middle East and Africa region continues to grow rapidly. "
    repeated = base_text * (target_tokens // 20)
    return repeated

contexts = {
    "32K": 32000,
    "64K": 64000,
    "128K": 128000,
}

print("=== Scenario E: Long Context Test ===")
for label, token_count in contexts.items():
    context = generate_long_context(token_count)
    prompt = f"Based on the following document, provide a 200-word executive summary:\n\n{context}"
    
    print(f"\n--- {label} input tokens ---")
    for i in range(3):
        result = benchmark_single(prompt, f"{label} Run {i+1}")
```

---

### Results Template

After running benchmarks, fill in this comparison table for the customer report:

| Metric | Token API (Baseline) | PTU | Improvement |
|--------|---------------------|-----|-------------|
| TTFT (P50) | ___ ms | ___ ms | ___% faster |
| TTFT (P99) | ___ ms | ___ ms | ___% faster |
| TPS (avg) | ___ | ___ | ___x faster |
| Max Concurrent (no 429) | ___ | ___ | ___x more |
| Sustained TPM (30min) | ___ | ___ | ___x higher |
| 429 Errors (burst 200) | ___/200 | ___/200 | ___% reduction |
| Cost per 1M tokens | $___  | $___ | ___% savings |

---

### Quick Comparison Script

Run this to compare Token API vs PTU side-by-side:

```python
import os

# Test both endpoints
configs = {
    "Token API": {
        "model": "qwen3.6-plus-2026-04-02",  # standard model ID
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    },
    "PTU": {
        "model": os.getenv("PTU_MODEL_ID"),  # PTU deployment model ID
        "base_url": os.getenv("BASE_URL")
    }
}

print("=== Side-by-Side Comparison ===")
for name, config in configs.items():
    print(f"\n--- {name} ---")
    # Run Scenario A with each config
    # (modify benchmark_single to accept model/base_url params)
```

---

### Customer-Facing Summary Template

After benchmarking, use this template for the customer:

```
Dear [Customer],

Here are the PTU benchmark results for your workload:

Performance:
- Response speed improved by [X]x (from [Y] TPS to [Z] TPS)
- First token latency reduced by [X]% (from [Y]ms to [Z]ms)
- Zero rate-limit errors under [X] concurrent requests

Cost Analysis (at your current volume of [X]M tokens/day):
- Current Token API cost: $[X]/day
- PTU cost (prepaid daily): $[Y]/day
- Monthly savings: $[Z] ([X]% reduction)

Recommendation:
Based on your traffic pattern of [describe], we recommend:
- [X] TPM input + [Y] TPM output (prepaid daily)
- Estimated monthly cost: $[Z]
- Break-even: [X] tokens/day (you currently use [Y])

Next steps:
1. Confirm purchase configuration
2. Place order on Model Studio console
3. Switch endpoint to PTU model ID
```

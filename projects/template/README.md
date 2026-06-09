# Project Template

Copy this directory to create a new project for a customer use case.

## Quick Start

```bash
# 1. Copy the template
cp -r projects/template projects/<project-name>

# 2. Edit project.yaml with your deployment details
#    (model code, deployment ID, TPM quotas, pricing)

# 3. Create a .env file for API credentials
cp .env.example projects/<project-name>/.env
#    Edit the .env with your DASHSCOPE_API_KEY

# 4. Run benchmarks against this project
python -m ptu_benchmark --project projects/<project-name>
#    Or with export:
python -m ptu_benchmark --project projects/<project-name> --export
```

## Files in a Project

| File | Purpose |
|------|---------|
| `project.yaml` | Deployment metadata (model, TPM, pricing) — **required** |
| `.env` | API key and connection settings (auto-loaded if present) |
| `README.md` | Notes about this specific project / customer |

## How --project Works

When you pass `--project projects/my-customer`:

1. The tool reads `projects/my-customer/project.yaml` for model/TPM/pricing info
2. It loads `projects/my-customer/.env` for the API key (falls back to root `.env`)
3. All benchmark results are exported into `projects/my-customer/results/`
4. The customer report template auto-populates with project-specific pricing

## Example: projects/qwen3.6-plus-2026-04-02_500K_100K/

The `projects/qwen3.6-plus-2026-04-02_500K_100K/` folder is an example project pre-filled with sample
deployment data from the Alibaba Cloud console. Use it as a reference.

---
title: Providers and experiment definitions
permalink: /providers/
---

# Providers and experiment definitions

An experiment selects one provider, one or more model identifiers, benchmark tasks, and execution settings. Each model-task combination becomes a job.

Start from [`infrastructure/templates/experiment_template.yaml`]({{ site.repository_url }}/blob/main/infrastructure/templates/experiment_template.yaml).

## Comparing quantized and unquantized candidates

Use identifiers that make the variant unambiguous and run the same tasks with the same harness arguments. For example, an Ollama comparison might use tags such as `model:7b-q4_K_M` and `model:3b-fp16` if those are the exact locally available variants. The labels are illustrative: use the tags your registry actually exposes.

For vLLM and llama.cpp, a provider instance serves one model, so the framework starts it separately for each entry in `models`. Use a precise Hugging Face model/revision for vLLM; for llama.cpp, each item in `models` should be the precise GGUF file path (it becomes that instance's `model_path`).

```yaml
name: model-size-vs-quantization
description: "Same tasks and few-shot settings for a local Ollama comparison."

provider:
  type: ollama
  options:
    manage: true
    gpus: false  # opt in only on a host with NVIDIA Container Toolkit
    pull_models:
      - example-large:Q4_K_M
      - example-small:fp16

models:
  - example-large:Q4_K_M
  - example-small:fp16

benchmarks: [arc_easy, boolq]
execution:
  mode: sequential
  workers: 1
extra_harness_args:
  num_fewshot: 5
```

Remove `limit` for a final score. Use a small `limit` only for a smoke test, and do not compare a limited run with a full run.

## Provider options

### vLLM

`model` is required and selects the model that the vLLM process serves. Other useful options are `tensor_parallel_size`, `gpu_memory_utilization`, `dtype`, `gpus`, `hf_token`, and `host_models_dir`. See [`vllm.yaml`]({{ site.repository_url }}/blob/main/infrastructure/configs/providers/vllm.yaml).

### Ollama

With `manage: true` (the default), the framework creates an Ollama container. `pull_models` lists the tags to pull after it is ready, and `models_volume` can preserve downloads between runs. With `manage: false`, it connects to `host` and `port` instead and never starts or stops Ollama. See [`ollama.yaml`]({{ site.repository_url }}/blob/main/infrastructure/configs/providers/ollama.yaml).

#### macOS / Apple Silicon

Apple GPUs are exposed through Metal rather than CUDA. To use Metal, install
and run Ollama directly on macOS; an Ollama container launched by Docker
Desktop is normally CPU-only. Keep the benchmark backend in Docker if desired,
but set Ollama to external mode and use Docker Desktop's host name:

```yaml
provider:
  type: ollama
  options:
    manage: false
    host: host.docker.internal
    port: 11434
```

When the backend runs natively on macOS, use `host: localhost` instead. Do not
set `gpus: true` for this setup: that option requests NVIDIA devices and is not
the mechanism used by Apple Metal.

### llama.cpp

`model_path` is required and points to a GGUF file. `context_length`, `gpu_layers`, and `threads` control the server. It runs one model per process. See [`llamacpp.yaml`]({{ site.repository_url }}/blob/main/infrastructure/configs/providers/llamacpp.yaml).

### OpenAI-compatible API

Set `endpoint`, `api_key` when required, and a fallback `model` name. This provider is unmanaged: it only connects to an already-running service. See [`openai_compatible.yaml`]({{ site.repository_url }}/blob/main/infrastructure/configs/providers/openai_compatible.yaml).

## Execution settings

Use `sequential` by default. In `parallel` mode, `workers` limits job concurrency, but local providers remain serialized unless you explicitly set `supports_concurrency: true`. Set that flag only for an endpoint that can safely handle concurrent requests.

`extra_harness_args` are passed through to `lm_eval`; common examples are `num_fewshot`, `batch_size`, and `limit`.

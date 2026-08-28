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

# Ollama uses a chat-completion endpoint. Choose generation tasks: multiple-choice
# tasks such as arc_easy require token log-likelihoods, which chat endpoints lack.
benchmarks: [gsm8k, truthfulqa_gen]
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

### Hugging Face (local Transformers)

The `huggingface` provider loads a model from Hugging Face through
`lm-evaluation-harness`'s native `hf` backend. It does not start a server or
container, and downloads model weights to the local Hugging Face cache.

```yaml
provider:
  type: huggingface
  options:
    model: google/gemma-3-1b-it
    device: mps       # cpu, mps (Apple Silicon), or cuda
    dtype: auto
```

Use `device: mps` when the backend runs natively on an Apple Silicon Mac. A
backend running in Docker cannot access Apple's Metal GPU, so use `cpu` there.

## Execution settings

`execution` controls how the jobs created from the model/benchmark matrix are scheduled:

```yaml
execution:
  mode: sequential   # sequential (default) or parallel
  workers: 1         # maximum number of jobs in parallel mode
```

If there are two models and two benchmarks, the experiment creates four jobs. With
`sequential`, they run one after another. With `parallel`, at most `workers` jobs
can be submitted at once. The provider still acts as a concurrency gate:
providers are serialized unless `provider.supports_concurrency: true` is set.
Only enable that flag for a server that can safely handle simultaneous requests;
it is normally false for local Ollama, vLLM, and llama.cpp instances. `workers`
must be at least 1 and has no effect in sequential mode.

`keep_alive` and `supports_concurrency` belong under `provider`, not under
`execution`. `keep_alive: true` leaves a managed provider running after the
experiment; it does not change the number of jobs running concurrently.

## `extra_harness_args`

`extra_harness_args` is an escape hatch for options belonging to
[`lm-evaluation-harness`](https://github.com/EleutherAI/lm-evaluation-harness),
not to this framework. The project currently pins `lm-eval==0.4.5`; the
authoritative options for that installed version are shown by `lm_eval --help`
and in the harness' [`simple_evaluate`/CLI argument definitions](https://github.com/EleutherAI/lm-evaluation-harness/tree/v0.4.5/lm_eval). The
available benchmark names are separate: use `benchmarks list` as described in
the [benchmark documentation](../benchmarks/).

Keys in this mapping become `lm_eval` flags by prefixing them with `--`.
Values are passed as strings. Boolean `true` adds the flag and boolean `false`
omits it; this means negated flags are not represented automatically. The
framework always supplies its own `--model`, `--model_args`, `--tasks`,
`--output_path`, and `--log_samples` values, so do not repeat those keys here.

`apply_chat_template: true` tells `lm-evaluation-harness` to format prompts
using the model's chat template. It is useful for chat or instruction-tuned
models when the task should be evaluated as a conversation. It is not required
merely because the provider exposes an OpenAI-compatible chat endpoint. Use it
only when the model has a suitable chat template and the serving stack supports
the resulting format; otherwise, leave it unset or set it to `false`.

Typical examples:

```yaml
extra_harness_args:
  limit: 50             # smoke test: evaluate only 50 examples
  num_fewshot: 5       # number of demonstrations (when the task supports it)
  batch_size: 1        # requests per inference batch; lower it if memory is tight
  apply_chat_template: true  # use the model's chat template for chat/instruction models
```

For a normal final comparison, remove `limit` (or use the same value for every
candidate). Other harness options such as `seed`, `gen_kw`, `include_path`,
and `trust_remote_code` may be useful depending on the task and provider, but
must be checked against the installed harness version and task requirements.

## LoadTesting tests

An experiment can also measure streamed chat-completion performance while the
number of simultaneous virtual users increases. Add a `load_testing` section;
each value in `concurrent_users` creates one load-test job for each model. `input` is sent
by every virtual user and `max_output_tokens` limits each response. The input
can be literal text or a `file://` URI. Files are read as UTF-8 before the test
starts, so every request uses exactly the same contents. Use
`file:///absolute/path/input.md` for an absolute path or
`file://./relative/path/input.txt` for a relative path resolved by the process
running the experiment (normally the backend container).

```yaml
models:
  - llama3.2:1b
load_testing:
  concurrent_users: [1, 2, 4, 8]
  input: "file://./experiments/inputs/transformers.md"
  max_output_tokens: 128
  requests_per_user: 2
  temperature: 0
  timeout_seconds: 120
```

Results appear in the web UI's **LoadTesting** tab. It reports TTFT (time to
first token), p95 total latency, aggregate output throughput, perceived
per-request output speed, and failed requests for each model/provider/user
level. Providers that do not include
completion-token usage in streaming responses use a word-count estimate for
output throughput, marked with an asterisk in the UI. This feature requires an
OpenAI-compatible `/v1/chat/completions` streaming endpoint; the local
Hugging Face provider is not supported.

`Aggregate tok/s` is the total serving capacity across the concurrent request
batch. `Decode tok/s` is the mean generation speed of an
individual response, measured from its first token until its final token. It is
not calculated by simply dividing aggregate throughput by the number of users.

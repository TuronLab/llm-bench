
# Load testing

**Load testing** measures how an OpenAI-compatible streaming chat endpoint behaves
when several requests are active at the same time. It is a burst test: it
compares configured concurrency levels, rather than simulating a sustained
production traffic pattern.

## Configuration

The `load_testing` section in an experiment creates one load-test job for every
model and every value in `concurrent_users`:

```yaml
load_testing:
  concurrent_users: [1, 2, 4, 8]
  input: "file://./experiments/inputs/load-testing-long-prompt.md"
  max_output_tokens: 128
  requests_per_user: 2
  timeout_seconds: 120

generation:
  temperature: 0.7
  top_p: 0.9
  max_tokens: 128
  frequency_penalty: 0
  presence_penalty: 0
  seed: 42
```

`input` can be literal text or a UTF-8 `.txt`/`.md` `file://` URI. When it is a
file, it is read once before the burst starts, so every request uses the same
prompt. `max_output_tokens` is passed to the provider as `max_tokens`.

> **Warning:** Values explicitly configured in `load_testing` override the
> corresponding values in the experiment-level `generation` block. Therefore,
> `load_testing.temperature` overrides `generation.temperature`, and
> `load_testing.max_output_tokens` overrides `generation.max_tokens`. If they
> are omitted, the experiment-level generation values are used.

For a given concurrency level:

```text
total requests = concurrent_users * requests_per_user
```

Thus, increasing `concurrent_users` also increases the total amount of work
when `requests_per_user` remains fixed. The test does not represent a fixed
number of total requests across all levels unless that is configured separately
in the experiment design.

## How requests are made

The runner uses a `ThreadPoolExecutor` with `max_workers=concurrent_users`.
It submits `total requests` streaming tasks and releases them through a shared
start gate so that the initial requests begin as close together as practical.
The executor limits the number of active requests to the configured concurrency
level; additional requests wait for a worker to become available.

Each task sends an HTTP `POST` request to the provider's
`/chat/completions` endpoint with a payload equivalent to:

```json
{
  "model": "model-name",
  "messages": [{"role": "user", "content": "prompt"}],
  "max_tokens": 128,
  "temperature": 0,
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

The response is consumed as Server-Sent Events. Content from each streamed
delta is accumulated until `[DONE]`. If the provider reports
`completion_tokens`, that usage value is used. Otherwise, output tokens are
estimated with `len(text.split())`, and the result is marked with
`tokens_estimated: true`.

## Per-request measurements

For each successful request, the runner records:

- **TTFT (time to first token):** time from sending the request until the first
  non-empty streamed content delta arrives. This includes provider queueing and
  prompt-processing time.
- **Latency:** time from sending the request until the stream finishes. It
  includes TTFT, queueing, and generation.
- **Output tokens:** reported completion tokens, or the fallback estimate.
- **Perceived output speed:** output tokens divided by the time from the first
  token until the stream finishes. It measures generation speed after the user
  has started receiving output; it does not include TTFT.

Requests that raise an HTTP, JSON, or value error are recorded as failed. They
contribute to the request and error counts, but not to successful-request
latency, TTFT, or speed aggregates.

## Aggregated metrics

The runner produces the following summary for each model/provider/concurrency
level:

- `requests`: total requests submitted for the level.
- `successful_requests` and `failed_requests`: request outcome counts.
- `error_rate`: `failed_requests / requests`.
- `wall_time_seconds`: time from starting the burst measurement until all
  submitted tasks have completed.
- `ttft_mean_seconds`: arithmetic mean of successful-request TTFT values.
- `ttft_p50_seconds` and `ttft_p95_seconds`: the median and 95th percentile of
  successful-request TTFT values.
- `latency_mean_seconds`, `latency_p50_seconds`, and `latency_p95_seconds`:
  mean, median, and 95th percentile of successful-request total latencies.
- `output_tokens`: sum of output tokens from successful requests.
- `output_tokens_per_second`: `output_tokens / wall_time_seconds`. This is the
  aggregate output throughput of the entire burst. Wall time includes waiting,
  TTFT, and generation, but individual TTFT values are not summed because
  requests may overlap or wait while another request is generating.
- `perceived_tokens_per_second_mean`: arithmetic mean of each successful
  request's perceived output speed.
- `perceived_tokens_per_second_p50`: median of those per-request speeds.

The aggregate throughput and perceived speed answer different questions:

```text
aggregate output tok/s = all successful output tokens / total burst time
perceived tok/s        = mean(tokens per request / that request's generation time)
```

Increasing concurrency can therefore raise TTFT and total latency while leaving
aggregate throughput nearly unchanged if the provider remains continuously busy
and its total serving capacity is saturated. A stable throughput does not mean
that the user experience is unchanged; the additional waiting is visible in
TTFT and latency.

## Interpretation and limitations

Results should be compared across concurrency levels using TTFT p95, latency
p95, error rate, aggregate output throughput, and perceived speed together.
The test is not a sustained load generator and does not model ramp-up, request
arrival rates, long-running sessions, or a fixed total request count. Very high
values of `concurrent_users` can also be limited by client threads, operating
system file descriptors, HTTP connections, provider queues, memory, or request
timeouts.

With the default backend, results are stored as JSON under `results/load_testing/`, with one file per
model. Benchmark results use the separate `results/benchmarks/` directory. With
`BENCHLAB_PERSISTENCE=sqlite`, both result types and experiment state are stored
in `results/benchlab.db` (or `BENCHLAB_SQLITE_PATH`).

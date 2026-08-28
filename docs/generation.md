---
title: Generation settings
permalink: /generation/
---

# Generation settings

Experiments can define common generation parameters under `generation`. These
settings are used by benchmark runs (through `gen_kwargs`) and by load tests
when the provider supports the corresponding OpenAI-compatible request field.

All fields are optional. When a field is omitted, the provider or evaluation
tool uses its own default. Omitted fields are not included in the result's
`extra_conf`, so the displayed configuration only contains values explicitly
chosen in the experiment.

```yaml
generation:
  temperature: 0       # optional; provider default when omitted
  top_p: 1              # optional; provider default when omitted
  max_tokens: 128       # optional; load-test output limit when omitted
  frequency_penalty: 0 # optional; range -2 to 2
  presence_penalty: 0  # optional; range -2 to 2
  seed: 42              # optional; provider-dependent reproducibility hint
```

The available parameters are:

- `temperature`: controls randomness. Must be greater than or equal to `0`.
- `top_p`: nucleus-sampling threshold. Must be between `0` and `1`.
- `max_tokens`: maximum number of generated tokens. Must be at least `1`.
- `frequency_penalty`: penalizes tokens according to how often they have
  already appeared. Accepted range: `-2` to `2`.
- `presence_penalty`: encourages introducing new tokens or topics. Accepted
  range: `-2` to `2`.
- `seed`: optional integer seed. Its effect depends on the provider and model.

For a fair comparison, use the same generation settings for every provider and
model whenever the providers implement them consistently. Provider-specific
serving options remain under each entry in `providers[].options`.

> **Warning:** For load tests, values explicitly set inside `load_testing` take
> precedence over the corresponding values in `generation`. In particular,
> `load_testing.temperature` overrides `generation.temperature`, and
> `load_testing.max_output_tokens` overrides `generation.max_tokens`. If those
> load-testing fields are omitted, the values from `generation` are used.

# Supported benchmarks

This framework delegates evaluation to [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness), an open-source framework for running LLM benchmarks locally. It does not implement or maintain benchmark logic itself.

The exact task list depends on the version of `lm-evaluation-harness` installed in the backend image, including any custom tasks added to that installation. Use the following command for the authoritative list in a running deployment:

```bash
docker compose run --rm cli benchmarks list
```

<details>
<summary>Common benchmarks included in the built-in fallback catalogue</summary>

| Benchmark | What it evaluates |
| --- | --- |
| `mmlu` | Broad multiple-choice knowledge and reasoning across academic subjects. |
| `gsm8k` | Grade-school mathematical reasoning expressed in natural language. |
| `truthfulqa_mc2` | Truthfulness in multiple-choice answers, especially resistance to common misconceptions. |
| `arc_easy` | Elementary science questions from AI2 Reasoning Challenge. |
| `arc_challenge` | The more difficult split of AI2 Reasoning Challenge science questions. |
| `hellaswag` | Commonsense reasoning through sentence or situation continuation. |
| `winogrande` | Commonsense pronoun resolution with reduced dataset-specific shortcuts. |
| `piqa` | Physical commonsense reasoning about everyday situations. |
| `boolq` | Yes/no question answering grounded in a short passage. |
| `openbookqa` | Elementary science questions designed to require external facts and reasoning. |
| `humaneval` | Python code generation evaluated with unit tests. |
| `bbh` | BIG-Bench Hard: a collection of difficult reasoning tasks. |
| `gpqa` | Graduate-level, expert-domain multiple-choice questions. |
| `ifeval` | Whether generated responses follow explicit instructions. |

</details>

## Choosing a benchmark set

Use more than one task when comparing models. A small smoke test such as `arc_easy` and `boolq` is useful to validate configuration, but it is not a final comparison. Keep the same tasks, few-shot setting, and `limit` value for every candidate; a limited run should only be compared with another run using the same limit.

Some tasks need additional dependencies, datasets, credentials, or a capable code-execution setup. The harness reports such failures in the corresponding job log without stopping the rest of the experiment.

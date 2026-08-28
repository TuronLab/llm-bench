import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

const STEPS = ["Provider", "Benchmarks", "Load testing", "Review"];
const FALLBACK_BENCHMARKS = [
  "mmlu", "gsm8k", "truthfulqa_mc2", "arc_challenge", "arc_easy",
  "hellaswag", "winogrande", "piqa", "boolq", "openbookqa",
  "humaneval", "bbh", "gpqa", "ifeval",
];

export default function ExperimentBuilder() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [providersData, setProvidersData] = useState(null);
  const [benchmarksList, setBenchmarksList] = useState([]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const [name, setName] = useState("");
  const [providerType, setProviderType] = useState("");
  const [providerOptions, setProviderOptions] = useState({});
  const [modelInput, setModelInput] = useState("");
  const [models, setModels] = useState([]);
  const [benchmarkFilter, setBenchmarkFilter] = useState("");
  const [selectedBenchmarks, setSelectedBenchmarks] = useState([]);
  const [harnessLimit, setHarnessLimit] = useState("");
  const [applyChatTemplate, setApplyChatTemplate] = useState(false);
  const [extraHarnessArgs, setExtraHarnessArgs] = useState("");
  const [mode, setMode] = useState("sequential");
  const [workers, setWorkers] = useState(2);
  const [loadTestingEnabled, setLoadTestingEnabled] = useState(false);
  const [concurrentUsers, setConcurrentUsers] = useState("1, 2, 4, 8");
  const [loadTestingInput, setLoadTestingInput] = useState("");
  const [maxOutputTokens, setMaxOutputTokens] = useState(128);
  const [requestsPerUser, setRequestsPerUser] = useState(1);
  const [temperature, setTemperature] = useState(0);
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);

  useEffect(() => {
    api.listProviders().then((d) => {
      setProvidersData(d);
      setProviderType(d.types[0]);
    }).catch((e) => setError(e.message));
    // Keep the selector useful during a temporary API/proxy outage. The API
    // normally returns the complete harness registry; this curated fallback
    // mirrors the backend's fallback list.
    api.listBenchmarks()
      .then((d) => setBenchmarksList(d.benchmarks || FALLBACK_BENCHMARKS))
      .catch(() => setBenchmarksList(FALLBACK_BENCHMARKS));
  }, []);

  if (!providersData) return <div className="panel">{error || "Loading..."}</div>;

  const fields = providersData.schemas[providerType] || [];

  const updateOption = (key, value) => setProviderOptions((prev) => ({ ...prev, [key]: value }));

  const addModel = () => {
    if (modelInput.trim() && !models.includes(modelInput.trim())) {
      setModels([...models, modelInput.trim()]);
      setModelInput("");
    }
  };
  const removeModel = (m) => setModels(models.filter((x) => x !== m));

  const toggleBenchmark = (b) => {
    setSelectedBenchmarks((prev) =>
      prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]
    );
  };

  const visibleBenchmarks = benchmarksList
    .filter((b) => b.toLowerCase().includes(benchmarkFilter.toLowerCase()))
    .slice(0, 60);

  const parsedConcurrentUsers = concurrentUsers
    .split(",")
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isInteger(value) && value > 0);
  const hasValidLoadTesting = loadTestingEnabled
    && parsedConcurrentUsers.length > 0
    && parsedConcurrentUsers.length === concurrentUsers.split(",").filter((value) => value.trim()).length
    && Boolean(loadTestingInput.trim())
    && Number(maxOutputTokens) > 0
    && Number(requestsPerUser) > 0
    && Number(temperature) >= 0
    && Number(timeoutSeconds) > 0;

  const canProceed = () => {
    if (step === 0) return Boolean(name.trim()) && Boolean(providerType) && models.length > 0;
    if (step === 2) return selectedBenchmarks.length > 0 || hasValidLoadTesting;
    return true;
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      let additionalArgs = {};
      if (extraHarnessArgs.trim()) {
        additionalArgs = JSON.parse(extraHarnessArgs);
        if (!additionalArgs || Array.isArray(additionalArgs) || typeof additionalArgs !== "object") {
          throw new Error("Additional harness arguments must be a JSON object.");
        }
      }
      const harnessArgs = {
        ...(harnessLimit !== "" ? { limit: Number(harnessLimit) } : {}),
        ...(applyChatTemplate ? { apply_chat_template: true } : {}),
        ...additionalArgs,
      };
      const definition = {
        name,
        provider: { type: providerType, options: providerOptions },
        models,
        benchmarks: selectedBenchmarks,
        execution: { mode, workers: mode === "parallel" ? Number(workers) : 1 },
        extra_harness_args: harnessArgs,
        load_testing: loadTestingEnabled ? {
          concurrent_users: parsedConcurrentUsers,
          input: loadTestingInput.trim(),
          max_output_tokens: Number(maxOutputTokens),
          requests_per_user: Number(requestsPerUser),
          temperature: Number(temperature),
          timeout_seconds: Number(timeoutSeconds),
        } : undefined,
      };
      const record = await api.createExperiment(definition);
      await api.runExperiment(record.id);
      navigate(`/monitoring/${record.id}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <h1>New Experiment</h1>
      <p className="subtitle">Create an experiment without touching a YAML file.</p>

      <div className="wizard-steps">
        {STEPS.map((label, i) => (
          <div key={label} className={`wizard-step ${i === step ? "active" : i < step ? "done" : ""}`}>
            {i + 1}. {label}
          </div>
        ))}
      </div>

      <div className="panel">
        {step === 0 && (
          <div>
            <label>Experiment name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. llama3-vs-mistral" />

            <label>Provider</label>
            <select value={providerType} onChange={(e) => { setProviderType(e.target.value); setProviderOptions({}); }}>
              {providersData.types.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>

            {fields.filter((field) => field.key !== "model" && field.key !== "model_path").map((field) => (
              <div key={field.key}>
                <label>{field.label}{field.required ? " *" : ""}</label>
                {field.type === "boolean" ? (
                  <select
                    value={String(providerOptions[field.key] ?? field.default ?? false)}
                    onChange={(e) => updateOption(field.key, e.target.value === "true")}
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    type={field.type === "secret" ? "password" : field.type === "number" || field.type === "integer" ? "number" : "text"}
                    value={providerOptions[field.key] ?? field.default ?? ""}
                    onChange={(e) => updateOption(field.key, e.target.value)}
                  />
                )}
              </div>
            ))}

            <label style={{ marginTop: 20 }}>Models to test *</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={modelInput}
                onChange={(e) => setModelInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addModel()}
                placeholder="Model id, path, or tag"
              />
              <button type="button" onClick={addModel}>Add</button>
            </div>
            <div className="chip-list">
              {models.map((m) => (
                <span key={m} className="chip">
                  {m} <button type="button" onClick={() => removeModel(m)}>&times;</button>
                </span>
              ))}
              {models.length === 0 && <span className="empty-cell">No models added yet.</span>}
            </div>
          </div>
        )}

        {step === 1 && (
          <div>
            <label>Search benchmarks</label>
            <input value={benchmarkFilter} onChange={(e) => setBenchmarkFilter(e.target.value)} placeholder="e.g. mmlu" />
            <div className="chip-list">
              {visibleBenchmarks.map((b) => (
                <span
                  key={b}
                  className="chip"
                  style={{
                    cursor: "pointer",
                    borderColor: selectedBenchmarks.includes(b) ? "var(--accent)" : undefined,
                  }}
                  onClick={() => toggleBenchmark(b)}
                >
                  {selectedBenchmarks.includes(b) ? "✓ " : ""}{b}
                </span>
              ))}
            </div>
            <label style={{ marginTop: 20 }}>Selected ({selectedBenchmarks.length})</label>
            <div className="chip-list">
              {selectedBenchmarks.map((b) => (
                <span key={b} className="chip">
                  {b} <button type="button" onClick={() => toggleBenchmark(b)}>&times;</button>
                </span>
              ))}
            </div>

            <h2>Execution</h2>
            <label>Execution mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="sequential">Sequential</option>
              <option value="parallel">Parallel</option>
            </select>
            {mode === "parallel" && (
              <div>
                <label>Worker count</label>
                <input type="number" min={1} value={workers} onChange={(e) => setWorkers(e.target.value)} />
              </div>
            )}

            <label style={{ marginTop: 20 }}>Number of benchmark samples</label>
            <input
              type="number"
              min={1}
              value={harnessLimit}
              onChange={(e) => setHarnessLimit(e.target.value)}
              placeholder="Leave empty to use the full dataset"
            />
            <label className="checkbox-label">
              <input type="checkbox" checked={applyChatTemplate} onChange={(e) => setApplyChatTemplate(e.target.checked)} />
              Apply the model chat template
            </label>
            <label>Additional harness arguments (JSON)</label>
            <textarea
              rows="3"
              value={extraHarnessArgs}
              onChange={(e) => setExtraHarnessArgs(e.target.value)}
              placeholder={'e.g. {"log_samples": true}'}
            />
            <p className="field-help">Optional arguments are merged with the fields above.</p>
          </div>
        )}

        {step === 2 && (
          <div>
            <label className="checkbox-label">
              <input type="checkbox" checked={loadTestingEnabled} onChange={(e) => setLoadTestingEnabled(e.target.checked)} />
              Run a streaming load test alongside this experiment
            </label>
            <p className="subtitle">Measure response latency and throughput as the number of concurrent users grows.</p>

            {loadTestingEnabled && (
              <div>
                <label>Concurrent users *</label>
                <input
                  value={concurrentUsers}
                  onChange={(e) => setConcurrentUsers(e.target.value)}
                  placeholder="e.g. 1, 2, 4, 8"
                />
                <p className="field-help">Enter one or more positive whole numbers, separated by commas.</p>

                <label>Input prompt or file URI *</label>
                <textarea
                  rows="4"
                  value={loadTestingInput}
                  onChange={(e) => setLoadTestingInput(e.target.value)}
                  placeholder="Prompt text, or file://./experiments/inputs/prompt.md"
                />

                <label>Maximum output tokens</label>
                <input type="number" min={1} value={maxOutputTokens} onChange={(e) => setMaxOutputTokens(e.target.value)} />

                <label>Requests per user</label>
                <input type="number" min={1} value={requestsPerUser} onChange={(e) => setRequestsPerUser(e.target.value)} />

                <label>Temperature</label>
                <input type="number" min={0} step="0.1" value={temperature} onChange={(e) => setTemperature(e.target.value)} />

                <label>Timeout (seconds)</label>
                <input type="number" min={0.1} step="0.1" value={timeoutSeconds} onChange={(e) => setTimeoutSeconds(e.target.value)} />
              </div>
            )}
          </div>
        )}

        {step === 3 && (
          <div>
            <h2 style={{ marginTop: 0 }}>Review</h2>
            <table>
              <tbody>
                <tr><th>Name</th><td>{name}</td></tr>
                <tr><th>Provider</th><td>{providerType}</td></tr>
                <tr><th>Models</th><td>{models.join(", ")}</td></tr>
                <tr><th>Benchmarks</th><td>{selectedBenchmarks.join(", ")}</td></tr>
                <tr><th>Execution</th><td>{mode}{mode === "parallel" ? ` (${workers} workers)` : ""}</td></tr>
                <tr><th>Harness options</th><td>{harnessLimit ? `limit=${harnessLimit}` : "Full dataset"}{applyChatTemplate ? ", chat template" : ""}</td></tr>
                <tr><th>Load testing</th><td>{loadTestingEnabled ? `${parsedConcurrentUsers.join(", ")} concurrent users` : "Not included"}</td></tr>
                <tr><th>Total jobs</th><td>{models.length * (selectedBenchmarks.length + (loadTestingEnabled ? parsedConcurrentUsers.length : 0))}</td></tr>
              </tbody>
            </table>
          </div>
        )}

        {error && <div className="error-text">{error}</div>}

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 24 }}>
          <button type="button" className="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>
            Back
          </button>
          {step < STEPS.length - 1 ? (
            <button type="button" disabled={!canProceed()} onClick={() => setStep(step + 1)}>
              Next
            </button>
          ) : (
            <button type="button" disabled={submitting} onClick={submit}>
              {submitting ? "Launching..." : "Launch Experiment"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const BASE_URL = "/api/v1";

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  listProviders: () => request("/providers"),
  listModels: (providerType, params) =>
    request(`/providers/${providerType}/models?${new URLSearchParams(params)}`),
  listBenchmarks: () => request("/benchmarks"),

  listExperiments: () => request("/experiments"),
  getExperiment: (id) => request(`/experiments/${id}`),
  createExperiment: (definition) =>
    request("/experiments", { method: "POST", body: JSON.stringify(definition) }),
  runExperiment: (id) => request(`/experiments/${id}/run`, { method: "POST" }),
  cancelExperiment: (id) => request(`/experiments/${id}/cancel`, { method: "POST" }),
  getJobLogs: (experimentId, jobId, tail = 500) =>
    request(`/experiments/${experimentId}/logs/${jobId}?tail=${tail}`),

  getResultsMatrix: () => request(`/results?_=${Date.now()}`),
  getScalabilityResults: () => request("/results/scalability"),
  getModelResults: (model) => request(`/results/${encodeURIComponent(model)}`),
  getDetailedResult: (model, benchmark) =>
    request(`/results/${encodeURIComponent(model)}/${encodeURIComponent(benchmark)}`),
  deleteDetailedResult: (model, benchmark, timestamp) =>
    request(`/results/${encodeURIComponent(model)}/${encodeURIComponent(benchmark)}?timestamp=${encodeURIComponent(timestamp)}`, { method: "DELETE" }),
  deleteScalabilityResult: (result) => request(`/results/scalability/${encodeURIComponent(result.model)}/${encodeURIComponent(result.provider)}/${result.users}?timestamp=${encodeURIComponent(result.timestamp)}`, { method: "DELETE" }),
};

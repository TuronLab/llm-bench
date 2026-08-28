import React, { useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api/client.js";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export default function LiveMonitoring() {
  const { experimentId } = useParams();
  const [experiments, setExperiments] = useState([]);
  const [selectedId, setSelectedId] = useState(experimentId || null);
  const [record, setRecord] = useState(null);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [elapsedTick, setElapsedTick] = useState(Date.now());
  // Keep the display monotonic when a poll briefly returns an older status or
  // timestamp than the previous response.
  const elapsedByExperiment = useRef({});
  const elapsedStartByExperiment = useRef({});

  useEffect(() => {
    api.listExperiments().then((d) => {
      setExperiments(d.experiments);
      if (!selectedId && d.experiments.length > 0) {
        const running = d.experiments.find((e) => e.status === "running") || d.experiments[0];
        setSelectedId(running.id);
      }
    });
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    const load = () => api.getExperiment(selectedId).then(setRecord).catch((e) => setError(e.message));
    load();
    const interval = setInterval(load, 2500);
    return () => clearInterval(interval);
  }, [selectedId]);

  useEffect(() => {
    const tick = setInterval(() => setElapsedTick(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    if (!selectedId || !selectedJobId) return;
    const load = () =>
      api.getJobLogs(selectedId, selectedJobId).then((d) => setLogs(d.lines)).catch(() => setLogs([]));
    load();
    const interval = setInterval(load, 2000);
    return () => clearInterval(interval);
  }, [selectedId, selectedJobId]);

  const summary = useMemo(() => {
    if (!record) return null;
    const counts = { pending: 0, starting_provider: 0, running: 0, completed: 0, failed: 0, cancelled: 0 };
    record.jobs.forEach((j) => { counts[j.status] = (counts[j.status] || 0) + 1; });
    const done = counts.completed + counts.failed + counts.cancelled;
    const total = record.jobs.length || 1;
    return { counts, done, total, pct: Math.round((done / total) * 100) };
  }, [record]);

  const currentJob = record?.jobs.find((j) => j.status === "running");

  const cancel = async () => {
    if (!selectedId) return;
    await api.cancelExperiment(selectedId);
  };

  return (
    <div>
      <h1>Live Monitoring</h1>
      <p className="subtitle">Auto-refreshing every ~2.5s while an experiment runs.</p>

      <div className="panel">
        <label>Experiment</label>
        <select value={selectedId || ""} onChange={(e) => { setSelectedId(e.target.value); setSelectedJobId(null); }}>
          {experiments.map((e) => (
            <option key={e.id} value={e.id}>{e.name} ({e.status}) - {e.id}</option>
          ))}
        </select>
      </div>

      {error && <div className="panel error-text">{error}</div>}

      {record && summary && (
        <>
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{record.definition.name}</strong>{" "}
                <span className={`badge ${record.status}`}>{record.status}</span>
              </div>
              {!TERMINAL.has(record.status) && (
                <button className="danger" onClick={cancel}>Cancel Experiment</button>
              )}
            </div>

            <div style={{ marginTop: 14 }}>
              <div className="progress-bar"><div className="progress-bar-fill" style={{ width: `${summary.pct}%` }} /></div>
              <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 6 }}>
                {summary.done} / {summary.total} jobs finished ({summary.pct}%)
              </div>
            </div>

            <div className="grid-2" style={{ marginTop: 18 }}>
              <div>
                <div style={{ fontSize: 13, color: "var(--muted)" }}>Currently running</div>
                <div>{currentJob ? `${currentJob.model} · ${currentJob.benchmark}` : "-"}</div>
              </div>
              <div>
                <div style={{ fontSize: 13, color: "var(--muted)" }}>Elapsed</div>
                <div>{formatElapsed(record.started_at || record.created_at, record.updated_at, record.status, elapsedTick, elapsedByExperiment.current, elapsedStartByExperiment.current, record.id)}</div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
              {Object.entries(summary.counts).map(([status, count]) => (
                count > 0 && <span key={status} className={`badge ${status}`}>{count} {status}</span>
              ))}
            </div>
          </div>

          <div className="panel">
            <h2 style={{ marginTop: 0 }}>Jobs</h2>
            <table>
              <thead>
                <tr><th>Model</th><th>Benchmark</th><th>Status</th><th>Error</th><th></th></tr>
              </thead>
              <tbody>
                {record.jobs.map((job) => (
                  <tr key={job.id}>
                    <td>{job.model}</td>
                    <td>{job.benchmark}</td>
                    <td><span className={`badge ${job.status}`}>{job.status}</span></td>
                    <td style={{ color: "var(--bad)", fontSize: 12 }}>{job.error || ""}</td>
                    <td>
                      <button className="secondary" onClick={() => setSelectedJobId(job.id)}>
                        Logs
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedJobId && (
            <div className="panel">
              <h2 style={{ marginTop: 0 }}>Execution logs — {selectedJobId}</h2>
              <div className="log-viewer">
                {logs.length > 0 ? logs.join("\n") : "No log output yet."}
              </div>
            </div>
          )}
        </>
      )}

      {!record && <div className="panel">Select an experiment above, or <Link to="/experiments/new">create one</Link>.</div>}
    </div>
  );
}

function formatElapsed(createdAt, updatedAt, status, tick, elapsedByExperiment, elapsedStartByExperiment, experimentId) {
  const start = new Date(createdAt).getTime();
  if (status === "queued") return "00:00:00";
  // Server timestamps can have clock skew and `updated_at` changes throughout
  // the run. Anchor running experiments to the first client observation so
  // the displayed timer is a real elapsed counter, never a countdown.
  if (status === "running" && elapsedStartByExperiment[experimentId] === undefined) {
    elapsedStartByExperiment[experimentId] = tick;
  }
  const anchor = elapsedStartByExperiment[experimentId];
  const end = TERMINAL.has(status) ? new Date(updatedAt).getTime() : tick;
  const measuredSeconds = anchor !== undefined
    ? Math.max(0, Math.round(((TERMINAL.has(status) ? Math.max(end, anchor) : tick) - anchor) / 1000))
    : Math.max(0, Math.round((end - start) / 1000));
  const seconds = Math.max(measuredSeconds, elapsedByExperiment[experimentId] || 0);
  elapsedByExperiment[experimentId] = seconds;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
}

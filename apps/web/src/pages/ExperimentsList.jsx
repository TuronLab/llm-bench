import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";

const STATUS_ORDER = ["running", "queued", "failed", "completed", "cancelled", "draft"];

export default function ExperimentsList() {
  const [experiments, setExperiments] = useState(null);
  const [error, setError] = useState(null);

  const load = () => api.listExperiments().then((d) => setExperiments(d.experiments)).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <div className="panel error-text">{error}</div>;
  if (!experiments) return <div className="panel">Loading...</div>;

  const sorted = [...experiments].sort(
    (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status)
  );

  return (
    <div>
      <h1>Experiments</h1>
      <p className="subtitle">All experiments, most actionable first.</p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Jobs</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((exp) => (
              <tr key={exp.id}>
                <td>{exp.name}</td>
                <td><span className={`badge ${exp.status}`}>{exp.status}</span></td>
                <td>
                  {Object.entries(exp.job_counts).map(([status, count]) => (
                    <span key={status} style={{ marginRight: 8 }}>
                      <span className={`badge ${status}`}>{count}</span>
                    </span>
                  ))}
                  {exp.total_jobs === 0 && <span className="empty-cell">0 jobs</span>}
                </td>
                <td>
                  <Link to={`/monitoring/${exp.id}`} style={{ color: "var(--accent)" }}>
                    View
                  </Link>
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr><td colSpan={4} className="empty-cell">No experiments yet. Create one to get started.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

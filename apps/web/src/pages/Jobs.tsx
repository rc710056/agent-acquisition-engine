import React, { useEffect, useState } from 'react';
import { Activity, RefreshCw, XCircle, CheckCircle2, Clock, AlertTriangle } from 'lucide-react';
import { api } from '../services/api';
import { AcquisitionJob } from '../types';

export const Jobs: React.FC = () => {
  const [jobs, setJobs] = useState<AcquisitionJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState<string | null>(null);

  const fetchJobs = async () => {
    try {
      const data = await api.listJobs();
      setJobs(data);
    } catch (err) {
      console.error('Failed to load jobs', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 2500);
    return () => clearInterval(interval);
  }, []);

  const handleCancel = async (jobId: string) => {
    setCancelling(jobId);
    try {
      await api.cancelJob(jobId);
      await fetchJobs();
    } catch (err) {
      console.error('Cancel failed', err);
    } finally {
      setCancelling(null);
    }
  };

  const getStatusBadge = (state: string) => {
    switch (state) {
      case 'completed':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950/40 text-emerald-400 border border-emerald-800/40">
            <CheckCircle2 className="w-3 h-3" />
            <span>COMPLETED</span>
          </span>
        );
      case 'downloading':
      case 'verifying':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-blue-950/40 text-blue-400 border border-blue-800/40 animate-pulse">
            <RefreshCw className="w-3 h-3 animate-spin" />
            <span>{state.toUpperCase()}</span>
          </span>
        );
      case 'queued':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-gray-800/40 text-gray-400 border border-gray-700/40">
            <Clock className="w-3 h-3" />
            <span>QUEUED</span>
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-red-950/40 text-red-400 border border-red-800/40">
            <AlertTriangle className="w-3 h-3" />
            <span>FAILED</span>
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-950/40 text-amber-400 border border-amber-800/40">
            <XCircle className="w-3 h-3" />
            <span>CANCELLED</span>
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amoled-hover text-gray-400 border border-amoled-border">
            {state.toUpperCase()}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Acquisition Jobs</h2>
          <p className="text-xs text-gray-400 mt-1">
            Real-time execution telemetry, state machine progression, byte transfer counters, and cancellation controls.
          </p>
        </div>
        <button
          onClick={fetchJobs}
          className="p-2 rounded-md bg-amoled-hover border border-amoled-border text-gray-400 hover:text-gray-200 transition-colors"
          title="Refresh Job List"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {loading ? (
        <div className="p-12 text-center text-xs text-gray-500 font-mono">Loading job telemetry...</div>
      ) : jobs.length === 0 ? (
        <div className="p-12 text-center rounded-xl border border-dashed border-amoled-border bg-amoled-card/20">
          <Activity className="w-8 h-8 text-gray-600 mx-auto mb-2" />
          <p className="text-xs text-gray-400">No acquisition jobs registered yet.</p>
          <p className="text-[11px] text-gray-600 mt-1">Submit a URL from the Workspace or call the MCP start_acquisition tool.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-amoled-border bg-amoled-card/50 overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-amoled-input/80 border-b border-amoled-border text-[10px] font-mono text-gray-400 uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-4">Job ID</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Progress</th>
                  <th className="py-3 px-4">Operation</th>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-amoled-border/60">
                {jobs.map((job) => (
                  <tr key={job.job_id} className="hover:bg-amoled-hover/40 transition-colors">
                    <td className="py-3.5 px-4 font-mono text-electric-400 text-[11px]">
                      {job.job_id.slice(0, 12)}...
                    </td>
                    <td className="py-3.5 px-4">{getStatusBadge(job.state)}</td>
                    <td className="py-3.5 px-4 w-44">
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] font-mono text-gray-400">
                          <span>{job.progress_percent.toFixed(0)}%</span>
                          <span>
                            {(job.bytes_transferred / 1024 / 1024).toFixed(2)} MB
                            {job.total_bytes ? ` / ${(job.total_bytes / 1024 / 1024).toFixed(2)} MB` : ''}
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-amoled-input rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-300 ${
                              job.state === 'completed'
                                ? 'bg-emerald-500'
                                : job.state === 'failed'
                                ? 'bg-red-500'
                                : 'bg-electric-500'
                            }`}
                            style={{ width: `${Math.min(job.progress_percent, 100)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-gray-300 text-[11px] max-w-xs truncate font-mono">
                      {job.error_message ? (
                        <span className="text-red-400">{job.error_message}</span>
                      ) : (
                        job.current_operation
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-gray-500 font-mono text-[10px]">
                      {new Date(job.created_at).toLocaleTimeString()}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      {['queued', 'downloading'].includes(job.state) && (
                        <button
                          onClick={() => handleCancel(job.job_id)}
                          disabled={cancelling === job.job_id}
                          className="px-2 py-1 rounded bg-amoled-input hover:bg-red-950/40 hover:text-red-400 border border-amoled-border text-[10px] text-gray-400 transition-colors"
                        >
                          {cancelling === job.job_id ? 'Cancelling...' : 'Cancel'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

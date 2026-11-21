import React, { useState, useEffect } from 'react';
import { Search, ArrowRight, ShieldAlert, Loader2, FileDown, AlertTriangle } from 'lucide-react';
import { api } from '../services/api';
import { SourceInspection, FormatOption, AcquisitionJob } from '../types';

export const Workspace: React.FC<{ onJobCreated: () => void }> = ({ onJobCreated }) => {
  const [url, setUrl] = useState('');
  const [inspecting, setInspecting] = useState(false);
  const [inspection, setInspection] = useState<SourceInspection | null>(null);
  const [formats, setFormats] = useState<FormatOption[]>([]);
  const [selectedFormat, setSelectedFormat] = useState<string>('original');
  const [preflightData, setPreflightData] = useState<{
    can_acquire: boolean;
    requires_approval: boolean;
    approval_reason: string | null;
    estimated_size_bytes: number | null;
    duplicate_artifact_id?: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [activeJob, setActiveJob] = useState<AcquisitionJob | null>(null);

  const handleInspect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setInspecting(true);
    setError(null);
    setInspection(null);
    setFormats([]);
    setPreflightData(null);

    try {
      const res = await api.inspectSource(url.trim());
      setInspection(res);
      if (res.is_permitted) {
        const fmts = await api.listFormats(res.source_id);
        setFormats(fmts);
        if (fmts.length > 0) {
          setSelectedFormat(fmts[0].format_id);
          const pf = await api.preflight(res.source_id, fmts[0].format_id);
          setPreflightData(pf);
        }
      } else if (res.errors.length > 0) {
        setError(res.errors.join('; '));
      }
    } catch (err: any) {
      setError(err.message || 'Inspection failed');
    } finally {
      setInspecting(false);
    }
  };

  const handleFormatChange = async (fmtId: string) => {
    setSelectedFormat(fmtId);
    if (inspection) {
      try {
        const pf = await api.preflight(inspection.source_id, fmtId);
        setPreflightData(pf);
      } catch (err: any) {
        console.error('Preflight check failed', err);
      }
    }
  };

  const handleStartAcquisition = async () => {
    if (!inspection) return;
    setStarting(true);
    setError(null);

    try {
      const job = await api.createJob(inspection.source_id, selectedFormat);
      setActiveJob(job);
      onJobCreated();
    } catch (err: any) {
      setError(err.message || 'Failed to start acquisition');
    } finally {
      setStarting(false);
    }
  };

  // Poll active job status if present
  useEffect(() => {
    if (!activeJob || ['completed', 'failed', 'cancelled'].includes(activeJob.state)) return;

    const interval = setInterval(async () => {
      try {
        const updated = await api.getJob(activeJob.job_id);
        setActiveJob(updated);
      } catch (e) {
        console.error('Failed to poll active job', e);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeJob]);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Acquisition Workspace</h2>
        <p className="text-xs text-gray-400 mt-1">
          Inspect external target sources, evaluate SSRF safety, review available stream formats, and trigger cloud acquisition.
        </p>
      </div>

      {/* Target URL Input */}
      <form onSubmit={handleInspect} className="relative">
        <div className="flex items-center rounded-lg border border-amoled-border bg-amoled-input px-3 py-2 shadow-inner focus-within:border-electric-500/50 focus-within:ring-1 focus-within:ring-electric-500/20 transition-all">
          <Search className="w-4 h-4 text-gray-500 mr-2 shrink-0" />
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste target document or media URL (e.g. https://arxiv.org/pdf/2301.00001.pdf)"
            className="w-full bg-transparent text-xs text-gray-100 placeholder-gray-500 focus:outline-none"
            required
          />
          <button
            type="submit"
            disabled={inspecting || !url.trim()}
            className="ml-2 px-3 py-1.5 rounded-md bg-electric-600 hover:bg-electric-500 disabled:opacity-50 text-xs font-medium text-white flex items-center space-x-1.5 shrink-0 transition-colors shadow-sm"
          >
            {inspecting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Inspecting...</span>
              </>
            ) : (
              <>
                <span>Inspect Source</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </form>

      {/* Error Banner */}
      {error && (
        <div className="p-3 rounded-lg bg-red-950/30 border border-red-800/40 text-red-300 text-xs flex items-start space-x-2">
          <ShieldAlert className="w-4 h-4 shrink-0 text-red-400 mt-0.5" />
          <div>
            <p className="font-medium">Acquisition Request Blocked or Failed</p>
            <p className="text-red-400/90 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Inspection Results Card */}
      {inspection && (
        <div className="p-5 rounded-xl border border-amoled-border bg-amoled-card/60 space-y-4 shadow-xl">
          <div className="flex items-center justify-between border-b border-amoled-border pb-3">
            <div className="flex items-center space-x-2">
              <span className={`w-2 h-2 rounded-full ${inspection.is_permitted ? 'bg-emerald-500' : 'bg-red-500'}`} />
              <span className="text-xs font-mono text-gray-300">SOURCE: {inspection.source_id}</span>
              {inspection.source_type && (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-electric-950/60 text-electric-400 border border-electric-800/50">
                  {inspection.source_type}
                </span>
              )}
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium tracking-wide uppercase bg-amoled-hover text-gray-400 border border-amoled-border">
              {inspection.provider_id}
            </span>
          </div>

          {/* Media Header / Thumbnail preview if present */}
          {(inspection.title || inspection.thumbnail_url) && (
            <div className="flex items-center space-x-3 p-3 rounded-lg bg-amoled-input/30 border border-amoled-border">
              {inspection.thumbnail_url && (
                <img
                  src={inspection.thumbnail_url}
                  alt="Source Thumbnail"
                  className="w-16 h-16 rounded object-cover border border-amoled-border shrink-0"
                />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-gray-100 truncate">{inspection.title || 'Discovered Media'}</p>
                {inspection.resolved_url && (
                  <p className="text-[11px] font-mono text-gray-400 truncate mt-0.5">{inspection.resolved_url}</p>
                )}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div className="p-3 rounded-lg bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">Status</p>
              <p className={`mt-1 font-medium ${inspection.is_permitted ? 'text-emerald-400' : 'text-red-400'}`}>
                {inspection.is_permitted ? 'Permitted (Safe)' : 'Forbidden / Blocked'}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">MIME Type</p>
              <p className="mt-1 font-mono text-gray-200 truncate">{inspection.mime_type || 'Unknown'}</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">Estimated Size</p>
              <p className="mt-1 font-mono text-gray-200">
                {inspection.estimated_size_bytes
                  ? `${(inspection.estimated_size_bytes / 1024 / 1024).toFixed(2)} MB`
                  : 'Unknown (Stream)'}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">Capabilities</p>
              <p className="mt-1 font-mono text-gray-200 truncate">
                {inspection.capabilities.join(', ') || 'Standard Stream'}
              </p>
            </div>
          </div>

          {/* Preflight Advice Banner */}
          {preflightData?.requires_approval && (
            <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-800/40 text-amber-300 text-xs flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>{preflightData.approval_reason}</span>
            </div>
          )}

          {/* Format Selection & Launch */}
          {inspection.is_permitted && formats.length > 0 && (
            <div className="pt-2 border-t border-amoled-border flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <span className="text-xs text-gray-400">Target Format:</span>
                <select
                  value={selectedFormat}
                  onChange={(e) => handleFormatChange(e.target.value)}
                  className="bg-amoled-input border border-amoled-border text-xs text-gray-200 rounded px-2.5 py-1.5 focus:outline-none focus:border-electric-500"
                >
                  {formats.map((f) => (
                    <option key={f.format_id} value={f.format_id}>
                      {f.quality_label} {f.resolution ? `[${f.resolution}]` : ''} ({f.mime_type})
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={handleStartAcquisition}
                disabled={starting}
                className="px-4 py-2 rounded-md bg-electric-600 hover:bg-electric-500 disabled:opacity-50 text-xs font-semibold text-white flex items-center space-x-2 shadow-md transition-all"
              >
                {starting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />}
                <span>Dispatch Acquisition Job</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Active Job Progress in Workspace */}
      {activeJob && (
        <div className="p-4 rounded-xl border border-electric-500/30 bg-electric-600/10 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className={`w-2 h-2 rounded-full ${activeJob.state === 'completed' ? 'bg-emerald-500' : 'bg-electric-400 animate-pulse'}`} />
              <span className="font-semibold text-gray-100">
                Job {activeJob.job_id.slice(0, 12)}: {activeJob.state.toUpperCase()}
              </span>
            </div>
            <span className="font-mono text-electric-400">{activeJob.progress_percent.toFixed(0)}%</span>
          </div>

          <div className="w-full h-1.5 bg-amoled-input rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${activeJob.state === 'completed' ? 'bg-emerald-500' : 'bg-electric-500'}`}
              style={{ width: `${Math.min(activeJob.progress_percent, 100)}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
            <span>{activeJob.current_operation}</span>
            <span>{(activeJob.bytes_transferred / 1024 / 1024).toFixed(2)} MB transferred</span>
          </div>
        </div>
      )}
    </div>
  );
};

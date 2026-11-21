import React, { useState, useEffect } from 'react';
import {
  Search,
  ArrowRight,
  ShieldAlert,
  Loader2,
  FileDown,
  AlertTriangle,
  Film,
  Tv,
  CheckCircle2,
  ExternalLink,
  ShieldCheck
} from 'lucide-react';
import { api } from '../services/api';
import { SourceInspection, FormatOption, AcquisitionJob } from '../types';

interface WorkspaceProps {
  onJobCreated?: () => void;
  onNavigateToJobs?: () => void;
  onNavigateToFiles?: () => void;
}

export const Workspace: React.FC<WorkspaceProps> = ({ onJobCreated, onNavigateToJobs, onNavigateToFiles }) => {
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

  const quickSamples = [
    { label: '🎬 Movie: Iron Man', query: 'Iron Man' },
    { label: '🐰 Movie: Big Buck Bunny', query: 'Big Buck Bunny' },
    { label: '🎧 Audio: MP3 Stream', query: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3' },
    { label: '🧲 Torrent: Magnet Link', query: 'magnet:?xt=urn:btih:3b245504fb5f4a4227cac320dbdc293a5b3f3f57&dn=Big+Buck+Bunny+1080p&tr=https%3A%2F%2Ftorrent.ubuntu.com%3A443%2Fannounce' }
  ];

  const handleInspectWithUrl = async (targetQuery: string) => {
    setUrl(targetQuery);
    setInspecting(true);
    setError(null);
    setInspection(null);
    setFormats([]);
    setPreflightData(null);

    try {
      const res = await api.inspectSource(targetQuery.trim());
      setInspection(res);
      if (res.is_permitted) {
        const fmts = await api.listFormats(res.source_id);
        setFormats(fmts);
        if (fmts.length > 0) {
          const bestFmt = fmts.find((f) => f.format_id === 'best_video_audio') ||
                          fmts.find((f) => f.category === 'recommended') ||
                          fmts.find((f) => f.has_audio !== false && f.file_type === 'video') ||
                          fmts[0];
          setSelectedFormat(bestFmt.format_id);
          const pf = await api.preflight(res.source_id, bestFmt.format_id);
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

  const handleInspect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    await handleInspectWithUrl(url);
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
      const autoApprove = !!preflightData?.requires_approval;
      const job = await api.createJob(inspection.source_id, selectedFormat, undefined, autoApprove);
      setActiveJob(job);
      if (onJobCreated) {
        onJobCreated();
      }
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
    }, 1200);

    return () => clearInterval(interval);
  }, [activeJob]);

  const isMovie = inspection?.provider_id === 'movie_intelligence';

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Acquisition Workspace</h2>
        <p className="text-xs text-gray-400 mt-1">
          Inspect movies, videos, audio MP3s, magnet torrents, or direct URLs. Evaluate legal OTT platforms and dispatch high-speed chunked downloads.
        </p>
      </div>

      {/* Target Search / URL Input */}
      <div className="space-y-2.5">
        <form onSubmit={handleInspect} className="relative">
          <div className="flex items-center rounded-xl border border-amoled-border bg-amoled-input px-3.5 py-2.5 shadow-inner focus-within:border-electric-500/50 focus-within:ring-1 focus-within:ring-electric-500/20 transition-all">
            <Search className="w-4 h-4 text-gray-400 mr-2.5 shrink-0" />
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Enter movie title, media name, video URL, or magnet link (e.g. 'Iron Man', 'Big Buck Bunny', 'magnet:?...')"
              className="w-full bg-transparent text-xs text-gray-100 placeholder-gray-500 focus:outline-none"
              required
            />
            <button
              type="submit"
              disabled={inspecting || !url.trim()}
              className="ml-2 px-4 py-2 rounded-lg bg-electric-600 hover:bg-electric-500 disabled:opacity-50 text-xs font-semibold text-white flex items-center space-x-1.5 shrink-0 transition-all shadow-md shadow-electric-600/20"
            >
              {inspecting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Inspecting...</span>
                </>
              ) : (
                <>
                  <span>Inspect & Discover</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </div>
        </form>

        {/* Quick Sample Presets */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-[10px] font-mono text-gray-500 uppercase">Quick Samples:</span>
          {quickSamples.map((sample, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleInspectWithUrl(sample.query)}
              className="px-2.5 py-1 rounded-md bg-amoled-card/80 hover:bg-amoled-hover border border-amoled-border text-gray-300 hover:text-white text-[11px] font-medium transition-all"
            >
              {sample.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-red-950/30 border border-red-800/40 text-red-300 text-xs flex items-start space-x-2.5">
          <ShieldAlert className="w-4 h-4 shrink-0 text-red-400 mt-0.5" />
          <div>
            <p className="font-medium">Acquisition Request Blocked or Failed</p>
            <p className="text-red-400/90 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Inspection Results Card */}
      {inspection && (
        <div className="p-6 rounded-2xl border border-amoled-border bg-amoled-card/60 space-y-5 shadow-xl backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-amoled-border pb-3.5">
            <div className="flex items-center space-x-2.5">
              <span className={`w-2.5 h-2.5 rounded-full ${inspection.is_permitted ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
              <span className="text-xs font-mono text-gray-300">SOURCE: {inspection.source_id}</span>
              {inspection.source_type && (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-electric-950/60 text-electric-400 border border-electric-800/50">
                  {inspection.source_type}
                </span>
              )}
            </div>
            <span className="px-2.5 py-1 rounded text-[10px] font-mono font-medium tracking-wide uppercase bg-amoled-hover text-gray-300 border border-amoled-border">
              {inspection.provider_id.replace('_', ' ')}
            </span>
          </div>

          {/* Media Header / Cinematic Poster Preview */}
          {(inspection.title || inspection.thumbnail_url) && (
            <div className="flex flex-col sm:flex-row sm:items-center space-y-3 sm:space-y-0 sm:space-x-4 p-4 rounded-xl bg-amoled-input/40 border border-amoled-border">
              {inspection.thumbnail_url && (
                <img
                  src={inspection.thumbnail_url}
                  alt="Source Thumbnail"
                  className="w-20 h-24 rounded-lg object-cover border border-amoled-border shrink-0 shadow-md"
                />
              )}
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center space-x-2">
                  {isMovie && <Film className="w-4 h-4 text-electric-400 shrink-0" />}
                  <h3 className="text-sm font-semibold text-white truncate">{inspection.title || 'Discovered Media'}</h3>
                </div>
                {inspection.resolved_url && (
                  <p className="text-[11px] font-mono text-gray-400 truncate">{inspection.resolved_url}</p>
                )}
                {isMovie && (
                  <p className="text-[11px] text-gray-300 leading-relaxed pt-1">
                    Verified multi-stream cinematic asset. Synced 1080p/4K audio-video muxing, pure MP3 original score soundtrack, and P2P BitTorrent options available.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* OTT Legal Streaming Platform Guide (for Movies) */}
          {isMovie && (
            <div className="p-4 rounded-xl bg-gradient-to-r from-electric-950/40 to-amoled-card border border-electric-500/30 space-y-2">
              <div className="flex items-center space-x-2 text-xs font-semibold text-electric-300">
                <Tv className="w-4 h-4" />
                <span>OFFICIAL STREAMING & OTT CHANNELS</span>
              </div>
              <p className="text-[11px] text-gray-300">
                You can watch this title legally on official OTT platforms or proceed with offline acquisition below:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
                {(() => {
                  const titleLower = (inspection.title || '').toLowerCase();
                  const ottList = titleLower.includes('bunny')
                    ? [
                        { name: 'Blender Studio (Free Stream)', url: 'https://studio.blender.org' },
                        { name: 'YouTube (Free 4K 60fps)', url: 'https://www.youtube.com' },
                        { name: 'Internet Archive (Public Domain)', url: 'https://archive.org' }
                      ]
                    : titleLower.includes('interstellar')
                    ? [
                        { name: 'Paramount+ (4K HDR)', url: 'https://www.paramountplus.com' },
                        { name: 'Prime Video (Rent / Buy)', url: 'https://www.amazon.com/gp/video' },
                        { name: 'Apple TV (Dolby Atmos)', url: 'https://tv.apple.com' }
                      ]
                    : [
                        { name: 'Disney+ (4K HDR)', url: 'https://www.disneyplus.com' },
                        { name: 'Prime Video (Rent / Buy)', url: 'https://www.amazon.com/gp/video' },
                        { name: 'Apple TV (Dolby Atmos)', url: 'https://tv.apple.com' }
                      ];

                  return ottList.map((ott, i) => (
                    <a
                      key={i}
                      href={ott.url}
                      target="_blank"
                      rel="noreferrer"
                      className="p-2.5 rounded-lg bg-amoled-input border border-amoled-border hover:border-electric-500/50 flex items-center justify-between text-xs text-gray-200 transition-all group"
                    >
                      <span className="font-medium">{ott.name}</span>
                      <ExternalLink className="w-3.5 h-3.5 text-gray-400 group-hover:text-electric-400" />
                    </a>
                  ));
                })()}
              </div>
            </div>
          )}

          {/* Technical Specs Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">Safety Firewall</p>
              <p className={`mt-1 font-medium ${inspection.is_permitted ? 'text-emerald-400' : 'text-red-400'}`}>
                {inspection.is_permitted ? 'Permitted (SSRF Clean)' : 'Forbidden / Blocked'}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">MIME Type</p>
              <p className="mt-1 font-mono text-gray-200 truncate">{inspection.mime_type || 'Unknown'}</p>
            </div>
            <div className="p-3 rounded-xl bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">Estimated Size</p>
              <p className="mt-1 font-mono text-gray-200">
                {inspection.estimated_size_bytes
                  ? `${(inspection.estimated_size_bytes / 1024 / 1024).toFixed(2)} MB`
                  : 'Stream Dynamic'}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-amoled-input/50 border border-amoled-border">
              <p className="text-gray-500 text-[10px] uppercase font-mono">Capabilities</p>
              <p className="mt-1 font-mono text-gray-200 truncate">
                {inspection.capabilities.join(', ') || 'Direct Acquisition'}
              </p>
            </div>
          </div>

          {/* Preflight Approval Warning Banner */}
          {preflightData?.requires_approval && (
            <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-800/40 text-amber-300 text-xs flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>{preflightData.approval_reason}</span>
            </div>
          )}

          {/* Format Selection & Dispatch */}
          {inspection.is_permitted && formats.length > 0 && (() => {
            const currentFmt = formats.find((f) => f.format_id === selectedFormat) || formats[0];
            const recommended = formats.filter((f) => f.category === 'recommended' || (f.has_audio !== false && f.file_type === 'video'));
            const audioOnly = formats.filter((f) => f.category === 'audio_only' || f.file_type === 'audio');
            const otherFormats = formats.filter((f) => !recommended.includes(f) && !audioOnly.includes(f));

            return (
              <div className="pt-4 border-t border-amoled-border flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                  <div className="flex items-center space-x-2">
                    <span className="text-xs text-gray-300 font-medium">Format:</span>
                    <select
                      value={selectedFormat}
                      onChange={(e) => handleFormatChange(e.target.value)}
                      className="bg-amoled-input border border-amoled-border text-xs text-gray-100 rounded-lg px-3 py-2 focus:outline-none focus:border-electric-500 font-mono shadow-inner max-w-xs md:max-w-md truncate"
                    >
                      {recommended.length > 0 && (
                        <optgroup label="⭐ Video & Packages (Synchronized)">
                          {recommended.map((f) => (
                            <option key={f.format_id} value={f.format_id}>
                              {f.quality_label} ({f.mime_type})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {audioOnly.length > 0 && (
                        <optgroup label="🎧 Pure Audio (MP3 / FLAC)">
                          {audioOnly.map((f) => (
                            <option key={f.format_id} value={f.format_id}>
                              {f.quality_label} ({f.mime_type})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {otherFormats.length > 0 && (
                        <optgroup label="⚠️ Specialized Formats">
                          {otherFormats.map((f) => (
                            <option key={f.format_id} value={f.format_id}>
                              {f.quality_label} ({f.mime_type})
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>
                  </div>

                  {/* Audio/Video/Torrent Stream Indicator Pill */}
                  {currentFmt && (
                    <div className="flex items-center">
                      {currentFmt.file_type === 'archive' && (
                        <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-rose-950/70 border border-rose-800/50 text-rose-300">
                          🧲 P2P BitTorrent Package
                        </span>
                      )}
                      {currentFmt.has_audio !== false && currentFmt.file_type === 'video' && (
                        <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-emerald-950/70 border border-emerald-800/50 text-emerald-300">
                          🔊 Video + Audio Synced
                        </span>
                      )}
                      {currentFmt.file_type === 'audio' && (
                        <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-cyan-950/70 border border-cyan-800/50 text-cyan-300">
                          🎧 Pure Audio Track
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <button
                  onClick={handleStartAcquisition}
                  disabled={starting}
                  className={`px-5 py-2.5 rounded-xl ${
                    preflightData?.requires_approval
                      ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-600/30'
                      : 'bg-electric-600 hover:bg-electric-500 shadow-electric-600/30'
                  } disabled:opacity-50 text-xs font-semibold text-white flex items-center justify-center space-x-2 shadow-lg transition-all shrink-0`}
                >
                  {starting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : preflightData?.requires_approval ? (
                    <ShieldCheck className="w-4 h-4 text-white" />
                  ) : (
                    <FileDown className="w-4 h-4" />
                  )}
                  <span>
                    {preflightData?.requires_approval ? 'Approve & Dispatch' : 'Dispatch Acquisition'}
                  </span>
                </button>
              </div>
            );
          })()}
        </div>
      )}

      {/* Active Job Progress View */}
      {activeJob && (
        <div className={`p-5 rounded-2xl border space-y-3 text-xs shadow-xl backdrop-blur-md ${
          activeJob.state === 'failed'
            ? 'border-red-500/40 bg-gradient-to-br from-red-950/30 to-amoled-card'
            : activeJob.state === 'completed'
            ? 'border-emerald-500/40 bg-gradient-to-br from-emerald-950/30 to-amoled-card'
            : 'border-electric-500/40 bg-gradient-to-br from-electric-950/30 to-amoled-card'
        }`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <span className={`w-2.5 h-2.5 rounded-full ${
                activeJob.state === 'completed'
                  ? 'bg-emerald-400'
                  : activeJob.state === 'failed'
                  ? 'bg-red-400'
                  : 'bg-electric-400 animate-pulse'
              }`} />
              <span className="font-semibold text-white">
                Job {activeJob.job_id.slice(0, 12)}: {activeJob.state.toUpperCase()}
              </span>
            </div>
            <div className="flex items-center space-x-3">
              <span className="font-mono text-electric-300 font-bold">{activeJob.progress_percent.toFixed(0)}%</span>
              {onNavigateToJobs && (
                <button
                  type="button"
                  onClick={onNavigateToJobs}
                  className="text-[10px] font-mono text-electric-400 hover:text-electric-300 underline"
                >
                  View in Jobs &rarr;
                </button>
              )}
            </div>
          </div>

          <div className="w-full h-2 bg-amoled-input rounded-full overflow-hidden border border-amoled-border">
            <div
              className={`h-full transition-all duration-300 ${
                activeJob.state === 'completed'
                  ? 'bg-emerald-400'
                  : activeJob.state === 'failed'
                  ? 'bg-red-500'
                  : 'bg-gradient-to-r from-electric-600 to-electric-400'
              }`}
              style={{ width: `${Math.min(activeJob.progress_percent, 100)}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
            <span>{activeJob.current_operation}</span>
            <span>{(activeJob.bytes_transferred / 1024 / 1024).toFixed(2)} MB transferred</span>
          </div>

          {activeJob.state === 'failed' && activeJob.error_message && (
            <div className="p-3 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-xs">
              <span className="font-medium">Error: </span>{activeJob.error_message}
            </div>
          )}

          {activeJob.state === 'completed' && onNavigateToFiles && (
            <div className="pt-2 flex justify-end">
              <button
                onClick={onNavigateToFiles}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center space-x-2 transition-all shadow-md shadow-emerald-600/30"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Acquisition Complete — View in Vault</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

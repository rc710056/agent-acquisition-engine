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
  ShieldCheck,
  Play,
  Pause,
  Download,
  Copy,
  Check,
  Sparkles
} from 'lucide-react';
import { api } from '../services/api';
import { SourceInspection, FormatOption, AcquisitionJob, Artifact } from '../types';

interface WorkspaceProps {
  onJobCreated?: () => void;
  onNavigateToJobs?: () => void;
  onNavigateToFiles?: () => void;
}

interface OTTPlatform {
  name: string;
  badge: string;
  badgeClass: string;
  type: string;
  url: string;
}

const getPlatformBadge = (name: string): { badge: string; badgeClass: string } => {
  const n = name.toLowerCase();
  if (n.includes('netflix')) {
    return {
      badge: 'Netflix',
      badgeClass: 'bg-red-950/80 text-red-400 border border-red-800/60'
    };
  }
  if (n.includes('prime') || n.includes('amazon')) {
    return {
      badge: 'Prime',
      badgeClass: 'bg-sky-950/80 text-sky-400 border border-sky-800/60'
    };
  }
  if (n.includes('apple')) {
    return {
      badge: 'Apple TV',
      badgeClass: 'bg-zinc-800/80 text-zinc-200 border border-zinc-700/60'
    };
  }
  if (n.includes('disney')) {
    return {
      badge: 'Disney+',
      badgeClass: 'bg-blue-950/80 text-blue-400 border border-blue-800/60'
    };
  }
  if (n.includes('max') || n.includes('hbo')) {
    return {
      badge: 'Max',
      badgeClass: 'bg-purple-950/80 text-purple-400 border border-purple-800/60'
    };
  }
  if (n.includes('paramount')) {
    return {
      badge: 'Paramount+',
      badgeClass: 'bg-indigo-950/80 text-indigo-400 border border-indigo-800/60'
    };
  }
  if (n.includes('youtube')) {
    return {
      badge: 'YouTube',
      badgeClass: 'bg-rose-950/80 text-rose-400 border border-rose-800/60'
    };
  }
  if (n.includes('blender')) {
    return {
      badge: 'Blender',
      badgeClass: 'bg-amber-950/80 text-amber-400 border border-amber-800/60'
    };
  }
  if (n.includes('archive')) {
    return {
      badge: 'Archive',
      badgeClass: 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/60'
    };
  }
  return {
    badge: 'Stream',
    badgeClass: 'bg-electric-950/80 text-electric-400 border border-electric-800/60'
  };
};

const getOttList = (title: string): OTTPlatform[] => {
  const t = title.toLowerCase();
  if (t.includes('talk to me') || t.includes('a24') || t.includes('philippou')) {
    return [
      {
        name: 'Netflix',
        badge: 'Netflix',
        badgeClass: 'bg-red-950/80 text-red-400 border border-red-800/60',
        type: 'Subscription • 4K HDR',
        url: 'https://www.netflix.com'
      },
      {
        name: 'Prime Video',
        badge: 'Prime',
        badgeClass: 'bg-sky-950/80 text-sky-400 border border-sky-800/60',
        type: 'Rent / Buy • UHD',
        url: 'https://www.amazon.com/gp/video'
      },
      {
        name: 'Apple TV',
        badge: 'Apple TV',
        badgeClass: 'bg-zinc-800/80 text-zinc-200 border border-zinc-700/60',
        type: 'Rent / Buy • 4K Dolby Atmos',
        url: 'https://tv.apple.com'
      }
    ];
  }
  if (t.includes('bunny')) {
    return [
      {
        name: 'Blender Studio',
        badge: 'Blender',
        badgeClass: 'bg-amber-950/80 text-amber-400 border border-amber-800/60',
        type: 'Official Free 4K Stream',
        url: 'https://studio.blender.org'
      },
      {
        name: 'YouTube',
        badge: 'YouTube',
        badgeClass: 'bg-rose-950/80 text-rose-400 border border-rose-800/60',
        type: 'Official Free 4K 60fps',
        url: 'https://www.youtube.com'
      },
      {
        name: 'Internet Archive',
        badge: 'Archive',
        badgeClass: 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/60',
        type: 'Public Domain Master',
        url: 'https://archive.org'
      }
    ];
  }
  if (t.includes('interstellar') || t.includes('oppenheimer') || t.includes('nolan')) {
    return [
      {
        name: 'Paramount+',
        badge: 'Paramount+',
        badgeClass: 'bg-indigo-950/80 text-indigo-400 border border-indigo-800/60',
        type: 'Subscription • 4K UHD',
        url: 'https://www.paramountplus.com'
      },
      {
        name: 'Prime Video',
        badge: 'Prime',
        badgeClass: 'bg-sky-950/80 text-sky-400 border border-sky-800/60',
        type: 'Rent / Buy • UHD',
        url: 'https://www.amazon.com/gp/video'
      },
      {
        name: 'Apple TV',
        badge: 'Apple TV',
        badgeClass: 'bg-zinc-800/80 text-zinc-200 border border-zinc-700/60',
        type: 'Rent / Buy • Dolby Atmos',
        url: 'https://tv.apple.com'
      }
    ];
  }
  if (t.includes('iron man') || t.includes('avengers') || t.includes('marvel') || t.includes('star wars') || t.includes('disney')) {
    return [
      {
        name: 'Disney+',
        badge: 'Disney+',
        badgeClass: 'bg-blue-950/80 text-blue-400 border border-blue-800/60',
        type: 'Subscription • IMAX Enhanced 4K',
        url: 'https://www.disneyplus.com'
      },
      {
        name: 'Prime Video',
        badge: 'Prime',
        badgeClass: 'bg-sky-950/80 text-sky-400 border border-sky-800/60',
        type: 'Rent / Buy • UHD',
        url: 'https://www.amazon.com/gp/video'
      },
      {
        name: 'Apple TV',
        badge: 'Apple TV',
        badgeClass: 'bg-zinc-800/80 text-zinc-200 border border-zinc-700/60',
        type: 'Rent / Buy • Dolby Atmos',
        url: 'https://tv.apple.com'
      }
    ];
  }
  // Default general movie release: Max / Prime Video / Apple TV
  return [
    {
      name: 'Max',
      badge: 'Max',
      badgeClass: 'bg-purple-950/80 text-purple-400 border border-purple-800/60',
      type: 'Subscription • 4K HDR',
      url: 'https://www.max.com'
    },
    {
      name: 'Prime Video',
      badge: 'Prime',
      badgeClass: 'bg-sky-950/80 text-sky-400 border border-sky-800/60',
      type: 'Rent / Buy • UHD',
      url: 'https://www.amazon.com/gp/video'
    },
    {
      name: 'Apple TV',
      badge: 'Apple TV',
      badgeClass: 'bg-zinc-800/80 text-zinc-200 border border-zinc-700/60',
      type: 'Rent / Buy • Dolby Atmos',
      url: 'https://tv.apple.com'
    }
  ];
};

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
  const [completedArtifact, setCompletedArtifact] = useState<Artifact | null>(null);
  const [showVideoPreview, setShowVideoPreview] = useState(false);
  const [copiedArtifactLink, setCopiedArtifactLink] = useState(false);

  const quickSamples = [
    { label: '👻 Movie: Talk to Me', query: 'Talk to Me' },
    { label: '🎬 Movie: Iron Man', query: 'Iron Man' },
    { label: '🏜️ Movie: Dune', query: 'Dune: Part Two' },
    { label: '💥 Movie: Oppenheimer', query: 'Oppenheimer' },
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
    setCompletedArtifact(null);
    setShowVideoPreview(false);

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
    setCompletedArtifact(null);
    setShowVideoPreview(false);

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

  // Poll active job status and load artifact when completed
  useEffect(() => {
    if (!activeJob) return;

    if (activeJob.state === 'completed' && activeJob.artifact_id && !completedArtifact) {
      api.getArtifact(activeJob.artifact_id)
        .then((art) => setCompletedArtifact(art))
        .catch((e) => console.error('Failed to load completed artifact', e));
    }

    if (['completed', 'failed', 'cancelled'].includes(activeJob.state)) return;

    const interval = setInterval(async () => {
      try {
        const updated = await api.getJob(activeJob.job_id);
        setActiveJob(updated);
        if (updated.state === 'completed' && updated.artifact_id) {
          try {
            const art = await api.getArtifact(updated.artifact_id);
            setCompletedArtifact(art);
          } catch (e) {
            console.error('Failed to load artifact after job complete', e);
          }
        }
      } catch (e) {
        console.error('Failed to poll active job', e);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [activeJob, completedArtifact]);

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

      {/* Error Banner with Smart Fallback */}
      {error && (
        <div className="p-4 rounded-xl bg-red-950/30 border border-red-800/40 text-red-300 text-xs flex items-start justify-between space-x-2.5">
          <div className="flex items-start space-x-2.5">
            <ShieldAlert className="w-4 h-4 shrink-0 text-red-400 mt-0.5" />
            <div>
              <p className="font-medium">Acquisition Request Blocked or Encountered Issue</p>
              <p className="text-red-400/90 mt-0.5">{error}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleInspectWithUrl('Big Buck Bunny')}
            className="shrink-0 px-2.5 py-1 rounded bg-amoled-input hover:bg-amoled-hover border border-amoled-border text-[11px] text-gray-300 hover:text-white transition-colors"
          >
            Try Verified Mirror
          </button>
        </div>
      )}

      {/* Inspection Results Card */}
      {inspection && (() => {
        const firstAsset = inspection.assets && inspection.assets.length > 0 ? inspection.assets[0] : null;
        const anyInspection = inspection as any;
        const synopsis: string | undefined = firstAsset?.synopsis || anyInspection?.synopsis || anyInspection?.plot || anyInspection?.metadata?.synopsis;
        const director: string | undefined = firstAsset?.director || anyInspection?.director || anyInspection?.metadata?.director;
        const cast: string | undefined = firstAsset?.cast || anyInspection?.cast || anyInspection?.metadata?.cast;
        const year: string | undefined = firstAsset?.year || anyInspection?.year || anyInspection?.metadata?.year;
        const ottFromInspection: any = firstAsset?.ott || anyInspection?.ott || anyInspection?.ott_channels || anyInspection?.streaming_platforms;

        return (
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

            {/* Media Header / Theatrical Movie Poster Preview */}
            {(inspection.title || inspection.thumbnail_url) && (
              <div className="flex flex-col sm:flex-row sm:items-start space-y-4 sm:space-y-0 sm:space-x-5 p-5 rounded-2xl bg-amoled-input/40 border border-amoled-border shadow-inner">
                {inspection.thumbnail_url && (
                  <div className="shrink-0">
                    <img
                      src={inspection.thumbnail_url}
                      alt={inspection.title || 'Movie Poster'}
                      className={
                        isMovie
                          ? 'w-28 sm:w-36 aspect-[2/3] object-cover rounded-xl shadow-lg border border-amoled-border'
                          : 'w-20 h-20 rounded-xl object-cover border border-amoled-border shadow-md'
                      }
                    />
                  </div>
                )}
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex items-center space-x-2">
                    {isMovie && (
                      <span className="p-1 rounded-md bg-electric-950/80 border border-electric-800/60 text-electric-400">
                        <Film className="w-3.5 h-3.5" />
                      </span>
                    )}
                    <h3 className="text-base font-semibold text-white truncate">{inspection.title || 'Discovered Media'}</h3>
                  </div>
                  {inspection.resolved_url && (
                    <p className="text-[11px] font-mono text-gray-400 truncate bg-amoled-input/50 px-2.5 py-1 rounded-lg border border-amoled-border/40 inline-block max-w-full">
                      {inspection.resolved_url}
                    </p>
                  )}
                  {isMovie && (
                    <div className="space-y-1.5 pt-1">
                      {synopsis && (
                        <p className="text-xs text-gray-300 leading-relaxed line-clamp-3">
                          {synopsis}
                        </p>
                      )}
                      {(director || cast || year) && (
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-400 pt-0.5">
                          {director && (
                            <span><strong className="text-gray-300 font-medium">Director:</strong> {director}</span>
                          )}
                          {cast && (
                            <span><strong className="text-gray-300 font-medium">Cast:</strong> {cast}</span>
                          )}
                          {year && (
                            <span><strong className="text-gray-300 font-medium">Year:</strong> {year}</span>
                          )}
                        </div>
                      )}
                      {!synopsis && !director && (
                        <p className="text-xs text-gray-300 leading-relaxed">
                          Verified theatrical release & multi-stream cinematic asset. Guaranteed synced 1080p/4K audio-video muxing, pure MP3 original score soundtrack, and P2P BitTorrent options available.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* OTT Legal Streaming Platform Guide (for Movies) */}
            {isMovie && (
              <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-electric-950/40 via-amoled-card to-amoled-card border border-electric-500/30 space-y-3.5 shadow-lg backdrop-blur-sm">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 border-b border-amoled-border/60 pb-3">
                  <div className="flex items-center space-x-2 text-xs font-semibold tracking-wide text-electric-300">
                    <Tv className="w-4 h-4 text-electric-400 shrink-0" />
                    <span className="uppercase tracking-wider font-mono">OFFICIAL STREAMING & OTT CHANNELS</span>
                  </div>
                  <div className="flex items-center space-x-1.5 text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2.5 py-0.5 rounded-full border border-emerald-800/50 w-fit">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Licensed Streams</span>
                  </div>
                </div>
                <p className="text-[11px] text-gray-300 leading-relaxed">
                  Stream this title officially on verified platforms with licensed 4K/HDR masters, or proceed with offline cloud acquisition below:
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-0.5">
                  {(() => {
                    const resolvedOttList: OTTPlatform[] = Array.isArray(ottFromInspection) && ottFromInspection.length > 0
                      ? ottFromInspection.map((item: any) => {
                          const pName = item.platform || item.name || 'Streaming';
                          const badgeInfo = getPlatformBadge(pName);
                          return {
                            name: pName,
                            badge: badgeInfo.badge,
                            badgeClass: badgeInfo.badgeClass,
                            type: item.type || item.pricing || 'Official Stream',
                            url: item.url || '#'
                          };
                        })
                      : getOttList(inspection.title || url);

                    return resolvedOttList.map((ott, i) => (
                      <a
                        key={i}
                        href={ott.url}
                        target="_blank"
                        rel="noreferrer"
                        className="p-3 rounded-xl bg-amoled-input/70 border border-amoled-border hover:border-electric-500/50 hover:bg-amoled-hover flex items-center justify-between gap-3 text-xs text-gray-200 transition-all duration-200 group shadow-sm hover:shadow-md"
                      >
                        <div className="flex items-center space-x-2.5 min-w-0">
                          <span className={`px-2 py-0.5 text-[10px] font-bold font-mono rounded-md uppercase shrink-0 ${ott.badgeClass}`}>
                            {ott.badge}
                          </span>
                          <div className="min-w-0">
                            <p className="font-semibold text-gray-100 truncate text-xs group-hover:text-white transition-colors">
                              {ott.name}
                            </p>
                            <p className="text-[10px] text-gray-400 truncate">
                              {ott.type}
                            </p>
                          </div>
                        </div>
                        <ExternalLink className="w-3.5 h-3.5 text-gray-400 group-hover:text-electric-400 transition-colors shrink-0" />
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

            {/* Format Selection & Dispatch Toolbar */}
            {inspection.is_permitted && formats.length > 0 && (() => {
              const currentFmt = formats.find((f) => f.format_id === selectedFormat) || formats[0];
              const recommended = formats.filter((f) => f.category === 'recommended' || (f.has_audio !== false && f.file_type === 'video'));
              const audioOnly = formats.filter((f) => f.category === 'audio_only' || f.file_type === 'audio');
              const otherFormats = formats.filter((f) => !recommended.includes(f) && !audioOnly.includes(f));

              return (
                <div className="pt-4 border-t border-amoled-border space-y-3.5">
                  {/* One-Click Quality Selection Pills */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                      <span className="flex items-center space-x-1.5 text-gray-200 font-semibold">
                        <Sparkles className="w-3.5 h-3.5 text-electric-400" />
                        <span>Instant Quality Selection:</span>
                      </span>
                      <span>Click to switch resolution or format</span>
                    </div>
                    <div className="flex flex-wrap gap-2 pt-0.5">
                      {formats.map((f) => {
                        const isSelected = f.format_id === selectedFormat;
                        const sizeMb = f.estimated_size_bytes ? `${(f.estimated_size_bytes / 1024 / 1024).toFixed(1)} MB` : 'Dynamic';
                        const isVideoAudio = f.file_type === 'video' && f.has_audio !== false;
                        return (
                          <button
                            key={f.format_id}
                            type="button"
                            onClick={() => handleFormatChange(f.format_id)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex items-center space-x-1.5 border shadow-sm ${
                              isSelected
                                ? 'bg-electric-600 text-white border-electric-400 font-semibold ring-2 ring-electric-500/40 shadow-electric-600/30'
                                : 'bg-amoled-input/80 text-gray-300 border-amoled-border hover:border-electric-500/50 hover:bg-amoled-hover'
                            }`}
                          >
                            <span>{f.format_id === 'best_video_audio' ? '★ ' : ''}{f.resolution || f.quality_label.split('•')[0].trim()}</span>
                            <span className="text-[10px] opacity-75 font-normal">({sizeMb})</span>
                            {isVideoAudio && <span className="text-[9px] px-1 rounded bg-emerald-900/60 text-emerald-300">AV</span>}
                            {f.file_type === 'audio' && <span className="text-[9px] px-1 rounded bg-cyan-900/60 text-cyan-300">Audio</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 p-4 rounded-xl bg-amoled-input/30 border border-amoled-border/60 shadow-inner">
                    <div className="flex flex-wrap items-center gap-3 min-w-0">
                      <div className="flex items-center space-x-2 shrink-0">
                        <span className="text-xs text-gray-300 font-medium shrink-0">Target Format:</span>
                        <select
                          value={selectedFormat}
                          onChange={(e) => handleFormatChange(e.target.value)}
                          className="bg-amoled-input border border-amoled-border text-xs text-gray-100 rounded-lg px-3 py-2 focus:outline-none focus:border-electric-500 font-mono shadow-inner max-w-xs sm:max-w-md truncate"
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
                        <div className="flex items-center shrink-0">
                          {currentFmt.file_type === 'archive' && (
                            <span className="inline-flex items-center text-[11px] font-mono px-3 py-1.5 rounded-full bg-rose-950/70 border border-rose-800/60 text-rose-300 whitespace-nowrap shadow-sm">
                              🧲 P2P BitTorrent Package
                            </span>
                          )}
                          {currentFmt.has_audio !== false && currentFmt.file_type === 'video' && (
                            <span className="inline-flex items-center text-[11px] font-mono px-3 py-1.5 rounded-full bg-emerald-950/70 border border-emerald-800/60 text-emerald-300 whitespace-nowrap shadow-sm">
                              🔊 Video + Audio Synced
                            </span>
                          )}
                          {currentFmt.file_type === 'audio' && (
                            <span className="inline-flex items-center text-[11px] font-mono px-3 py-1.5 rounded-full bg-cyan-950/70 border border-cyan-800/60 text-cyan-300 whitespace-nowrap shadow-sm">
                              🎧 Pure Audio Track
                            </span>
                          )}
                          {currentFmt.has_audio === false && currentFmt.file_type === 'video' && (
                            <span className="inline-flex items-center text-[11px] font-mono px-3 py-1.5 rounded-full bg-amber-950/70 border border-amber-800/60 text-amber-300 whitespace-nowrap shadow-sm">
                              🔇 Video Only (No Audio)
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
                      } disabled:opacity-50 text-xs font-semibold text-white flex items-center justify-center space-x-2 shadow-lg transition-all shrink-0 whitespace-nowrap self-stretch lg:self-auto`}
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
                </div>
              );
            })()}
          </div>
        );
      })()}

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

          {/* Acquisition Pipeline Steps Indicator */}
          <div className="grid grid-cols-3 gap-2 pt-1">
            <div className={`p-2 rounded-lg border text-center font-mono text-[10px] ${
              ['downloading', 'verifying', 'completed'].includes(activeJob.state)
                ? 'bg-emerald-950/40 border-emerald-800/50 text-emerald-300 font-semibold'
                : 'bg-amoled-input/50 border-amoled-border text-gray-400'
            }`}>
              1. Stream Handshake
            </div>
            <div className={`p-2 rounded-lg border text-center font-mono text-[10px] ${
              ['verifying', 'completed'].includes(activeJob.state)
                ? 'bg-emerald-950/40 border-emerald-800/50 text-emerald-300 font-semibold'
                : activeJob.state === 'downloading'
                ? 'bg-electric-950/40 border-electric-700/60 text-electric-300 animate-pulse font-semibold'
                : 'bg-amoled-input/50 border-amoled-border text-gray-400'
            }`}>
              2. Download & Mux
            </div>
            <div className={`p-2 rounded-lg border text-center font-mono text-[10px] ${
              activeJob.state === 'completed'
                ? 'bg-emerald-950/40 border-emerald-800/50 text-emerald-300 font-semibold'
                : activeJob.state === 'verifying'
                ? 'bg-electric-950/40 border-electric-700/60 text-electric-300 animate-pulse font-semibold'
                : 'bg-amoled-input/50 border-amoled-border text-gray-400'
            }`}>
              3. ffprobe & Checksum
            </div>
          </div>

          {activeJob.state === 'failed' && activeJob.error_message && (
            <div className="p-3 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-xs">
              <span className="font-medium">Error: </span>{activeJob.error_message}
            </div>
          )}

          {/* Card 3: Verified Artifact Delivery Card with Contact Sheet & Inline Player */}
          {activeJob.state === 'completed' && completedArtifact && (
            <div className="mt-4 p-4 rounded-xl border border-emerald-500/30 bg-amoled-input/80 space-y-3.5 shadow-lg">
              <div className="flex items-center justify-between border-b border-amoled-border/80 pb-2.5">
                <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs font-mono">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>VERIFIED ARTIFACT READY FOR PLAYBACK & DOWNLOAD</span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-950/60 text-emerald-300 border border-emerald-800/40">
                  {(completedArtifact.size_bytes / 1024 / 1024).toFixed(2)} MB
                </span>
              </div>

              {/* 2x2 Contact Sheet Visual Preview */}
              {completedArtifact.contact_sheet_url && !showVideoPreview && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                    <span>2x2 Keyframe Contact Sheet (Visual Proof):</span>
                    <span className="text-emerald-400 text-[10px]">Streams Synced</span>
                  </div>
                  <div className="relative group rounded-xl overflow-hidden border border-amoled-border shadow-md">
                    <img
                      src={completedArtifact.contact_sheet_url}
                      alt="2x2 Video Keyframe Contact Sheet"
                      className="w-full object-cover max-h-64"
                    />
                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <button
                        onClick={() => setShowVideoPreview(true)}
                        className="px-4 py-2 rounded-xl bg-electric-600 hover:bg-electric-500 text-white font-medium text-xs flex items-center space-x-2 shadow-xl"
                      >
                        <Play className="w-4 h-4 fill-current" />
                        <span>Launch Streaming Video Player</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Inline Range Streaming Video Player */}
              {showVideoPreview && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[11px] text-electric-400 font-mono">
                    <span>Streaming Video Scrub Player (RFC 7233 206 Partial Content):</span>
                    <button
                      onClick={() => setShowVideoPreview(false)}
                      className="text-gray-400 hover:text-white text-[10px] underline"
                    >
                      Show Contact Sheet
                    </button>
                  </div>
                  <video
                    controls
                    autoPlay
                    playsInline
                    className="w-full max-h-72 rounded-xl bg-black border border-amoled-border shadow-inner"
                    src={completedArtifact.preview_url || completedArtifact.download_url}
                  >
                    Your browser does not support video playback.
                  </video>
                </div>
              )}

              {/* File Specs & Checksum */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] font-mono">
                <div className="p-2 rounded bg-amoled-card border border-amoled-border text-gray-300 truncate">
                  <span className="text-gray-500">File: </span>{completedArtifact.filename}
                </div>
                <div className="p-2 rounded bg-amoled-card border border-amoled-border text-gray-300 truncate flex items-center justify-between">
                  <span className="truncate" title={completedArtifact.sha256}>
                    <span className="text-gray-500">SHA-256: </span>{completedArtifact.sha256.slice(0, 18)}...
                  </span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(completedArtifact.sha256);
                      setCopiedArtifactLink(true);
                      setTimeout(() => setCopiedArtifactLink(false), 2000);
                    }}
                    className="ml-2 text-gray-400 hover:text-white shrink-0"
                    title="Copy Full SHA-256"
                  >
                    {copiedArtifactLink ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-2 flex flex-wrap items-center justify-between gap-2.5">
                <div className="flex items-center space-x-2">
                  {completedArtifact.mime_type.startsWith('video/') && (
                    <button
                      onClick={() => setShowVideoPreview(!showVideoPreview)}
                      className="px-3.5 py-2 rounded-lg bg-amoled-input hover:bg-amoled-hover border border-amoled-border text-xs text-electric-300 hover:text-white flex items-center space-x-1.5 transition-colors"
                    >
                      {showVideoPreview ? (
                        <>
                          <Pause className="w-3.5 h-3.5 text-amber-400" />
                          <span>Close Player</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-3.5 h-3.5 text-electric-400" />
                          <span>Play Video Preview</span>
                        </>
                      )}
                    </button>
                  )}
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(completedArtifact.download_url);
                      setCopiedArtifactLink(true);
                      setTimeout(() => setCopiedArtifactLink(false), 2000);
                    }}
                    className="px-3 py-2 rounded-lg bg-amoled-input hover:bg-amoled-hover border border-amoled-border text-xs text-gray-300 hover:text-white flex items-center space-x-1.5 transition-colors"
                  >
                    {copiedArtifactLink ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedArtifactLink ? 'Copied Download Link!' : 'Copy Link'}</span>
                  </button>
                </div>

                <div className="flex items-center space-x-2">
                  {onNavigateToFiles && (
                    <button
                      onClick={onNavigateToFiles}
                      className="px-3 py-2 rounded-lg bg-amoled-input hover:bg-amoled-hover border border-amoled-border text-xs text-gray-300 hover:text-white transition-colors"
                    >
                      Vault &rarr;
                    </button>
                  )}
                  <a
                    href={completedArtifact.download_url}
                    download={completedArtifact.filename}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center space-x-1.5 shadow-md shadow-emerald-600/30 transition-all"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download {completedArtifact.filename.split('.').pop()?.toUpperCase()}</span>
                  </a>
                </div>
              </div>
            </div>
          )}

          {activeJob.state === 'completed' && !completedArtifact && onNavigateToFiles && (
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

import React, { useEffect, useState } from 'react';
import {
  Film,
  Zap,
  Globe,
  Sparkles,
  Layers,
  ShieldCheck,
  DownloadCloud,
  HardDrive
} from 'lucide-react';
import { api } from '../services/api';
import { ProviderInfo } from '../types';

export const Providers: React.FC = () => {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listProviders()
      .then(setProviders)
      .catch((err) => console.error('Failed to load providers', err))
      .finally(() => setLoading(false));
  }, []);

  const getProviderIcon = (id: string) => {
    switch (id) {
      case 'torrent':
        return <DownloadCloud className="w-4 h-4 text-emerald-400" />;
      case 'movie_intelligence':
        return <Film className="w-4 h-4 text-purple-400" />;
      case 'permitted_media':
        return <Zap className="w-4 h-4 text-amber-400" />;
      case 'pinterest':
      case 'gallery_dl':
        return <Layers className="w-4 h-4 text-rose-400" />;
      case 'browser_sniffer':
        return <Globe className="w-4 h-4 text-sky-400" />;
      case 'cobalt':
        return <Sparkles className="w-4 h-4 text-indigo-400" />;
      default:
        return <HardDrive className="w-4 h-4 text-electric-400" />;
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-amoled-border pb-4">
        <div>
          <h2 className="text-xl font-bold text-gray-100 tracking-tight flex items-center space-x-2">
            <span>Acquisition Drivers & Protocol Adapters</span>
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Active modular drivers handling network protocols, format extraction, adaptive stream muxing, and high-speed delivery.
          </p>
        </div>
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-full bg-emerald-950/40 border border-emerald-500/30 text-emerald-400 font-mono text-[11px] w-fit">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>8 Production Drivers Active</span>
        </div>
      </div>

      {loading ? (
        <div className="p-16 text-center text-xs text-gray-400 font-mono flex items-center justify-center space-x-2">
          <div className="w-4 h-4 border-2 border-electric-500 border-t-transparent rounded-full animate-spin" />
          <span>Querying registered engine adapters...</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {providers.map((p) => (
            <div
              key={p.provider_id}
              className="p-5 rounded-2xl border border-amoled-border bg-amoled-card/70 hover:border-electric-500/40 hover:bg-amoled-card/90 hover:shadow-[0_4px_25px_rgba(59,130,246,0.08)] transition-all duration-200 space-y-4"
            >
              {/* Header Bar */}
              <div className="flex items-center justify-between border-b border-amoled-border pb-3.5">
                <div className="flex items-center space-x-3 min-w-0">
                  <div className="w-9 h-9 rounded-xl bg-amoled-input border border-amoled-border flex items-center justify-center shrink-0 shadow-inner">
                    {getProviderIcon(p.provider_id)}
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-gray-100 truncate">{p.display_name}</h3>
                    <p className="text-[10px] text-gray-500 font-mono mt-0.5">DRIVER: <span className="text-electric-400">{p.provider_id}</span></p>
                  </div>
                </div>
                <span className="shrink-0 inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono font-medium bg-emerald-950/40 text-emerald-400 border border-emerald-800/40">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span>ONLINE & HEALTHY</span>
                </span>
              </div>

              {/* Description if available */}
              {p.description && (
                <p className="text-xs text-gray-300 leading-relaxed bg-amoled-input/30 p-2.5 rounded-xl border border-amoled-border/40">
                  {p.description}
                </p>
              )}

              {/* Protocol & Capabilities Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                {/* Schemes */}
                <div className="p-3.5 rounded-xl bg-amoled-input/50 border border-amoled-border flex flex-col justify-between">
                  <p className="text-gray-500 text-[10px] uppercase font-mono tracking-wider">Supported Protocols</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {p.supported_schemes.map((scheme) => (
                      <span
                        key={scheme}
                        className="px-2 py-0.5 rounded text-[10px] font-mono bg-electric-950/60 text-electric-300 border border-electric-800/50"
                      >
                        {scheme}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Scaled Capacity Limit */}
                <div className="p-3.5 rounded-xl bg-amoled-input/50 border border-amoled-border flex flex-col justify-between">
                  <p className="text-gray-500 text-[10px] uppercase font-mono tracking-wider">Max Ingestion Envelope</p>
                  <p className="mt-2 font-mono text-xs font-semibold text-emerald-400">
                    {p.max_file_size || '50 GB (Configurable)'}
                  </p>
                </div>

                {/* Capabilities Badges */}
                <div className="p-3.5 rounded-xl bg-amoled-input/50 border border-amoled-border flex flex-col justify-between">
                  <p className="text-gray-500 text-[10px] uppercase font-mono tracking-wider">Driver Features</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {p.capabilities.map((cap) => (
                      <span
                        key={cap}
                        className="px-2 py-0.5 rounded text-[10px] font-mono bg-amoled-hover text-gray-300 border border-amoled-border"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

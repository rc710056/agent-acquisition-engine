import React, { useEffect, useState } from 'react';
import { Radio, CheckCircle2, Clock } from 'lucide-react';
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

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Acquisition Providers</h2>
        <p className="text-xs text-gray-400 mt-1">
          Modular driver adapters handling network protocols, format extraction, and streaming acquisition.
        </p>
      </div>

      {loading ? (
        <div className="p-12 text-center text-xs text-gray-500 font-mono">Querying registered provider drivers...</div>
      ) : (
        <div className="space-y-4">
          {providers.map((p) => (
            <div
              key={p.provider_id}
              className="p-5 rounded-xl border border-amoled-border bg-amoled-card/60 space-y-4 shadow-lg"
            >
              <div className="flex items-center justify-between border-b border-amoled-border pb-3">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-950/40 border border-emerald-800/40 flex items-center justify-center text-emerald-400">
                    <Radio className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold text-gray-200">{p.display_name}</h3>
                    <p className="text-[10px] text-gray-500 font-mono">ID: {p.provider_id}</p>
                  </div>
                </div>
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950/40 text-emerald-400 border border-emerald-800/40">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>HEALTHY</span>
                </span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-amoled-input/50 border border-amoled-border">
                  <p className="text-gray-500 text-[10px] uppercase font-mono">Supported Schemes</p>
                  <p className="mt-1 font-mono text-gray-300">{p.supported_schemes.join(', ')}</p>
                </div>
                <div className="p-3 rounded-lg bg-amoled-input/50 border border-amoled-border">
                  <p className="text-gray-500 text-[10px] uppercase font-mono">Max File Size</p>
                  <p className="mt-1 font-mono text-gray-300">500 MB (Enforced)</p>
                </div>
                <div className="p-3 rounded-lg bg-amoled-input/50 border border-amoled-border">
                  <p className="text-gray-500 text-[10px] uppercase font-mono">Capabilities</p>
                  <p className="mt-1 font-mono text-gray-300 truncate">{p.capabilities.join(', ')}</p>
                </div>
              </div>
            </div>
          ))}

          {/* Phase 2 Planned Provider Notice */}
          <div className="p-5 rounded-xl border border-dashed border-amoled-border bg-amoled-card/20 space-y-2 opacity-60">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2 text-xs font-medium text-gray-400">
                <Clock className="w-4 h-4" />
                <span>Permitted Media Provider (yt-dlp & FFmpeg)</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-amoled-input text-gray-500 border border-amoled-border">
                PHASE 2 TARGET
              </span>
            </div>
            <p className="text-[11px] text-gray-500">
              Audio and video stream metadata extraction and packaging. Currently scheduled for Phase 2 per development roadmap.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

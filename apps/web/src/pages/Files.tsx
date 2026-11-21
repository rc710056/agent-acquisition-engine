import React, { useEffect, useState } from 'react';
import { FileCheck, Download, ShieldCheck, Copy, Check } from 'lucide-react';
import { api } from '../services/api';
import { Artifact } from '../types';

export const Files: React.FC = () => {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const fetchArtifacts = async () => {
    try {
      const data = await api.listArtifacts();
      setArtifacts(data);
    } catch (err) {
      console.error('Failed to load artifacts', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArtifacts();
  }, []);

  const copySha = (sha: string, id: string) => {
    navigator.clipboard.writeText(sha);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Verified Artifact Vault</h2>
        <p className="text-xs text-gray-400 mt-1">
          Cryptographically checksummed documents and media assets delivered through expiring HMAC-signed download links.
        </p>
      </div>

      {loading ? (
        <div className="p-12 text-center text-xs text-gray-500 font-mono">Loading artifact vault...</div>
      ) : artifacts.length === 0 ? (
        <div className="p-12 text-center rounded-xl border border-dashed border-amoled-border bg-amoled-card/20">
          <FileCheck className="w-8 h-8 text-gray-600 mx-auto mb-2" />
          <p className="text-xs text-gray-400">Vault is empty.</p>
          <p className="text-[11px] text-gray-600 mt-1">Acquired and verified files will appear here automatically.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {artifacts.map((art) => (
            <div
              key={art.artifact_id}
              className="p-4 rounded-xl border border-amoled-border bg-amoled-card/60 hover:border-amoled-border/80 transition-all space-y-3 shadow-lg"
            >
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <h3 className="text-xs font-semibold text-gray-200 truncate max-w-xs">{art.filename}</h3>
                  <div className="flex items-center space-x-2 text-[10px] text-gray-500 font-mono">
                    <span>{(art.size_bytes / 1024 / 1024).toFixed(2)} MB</span>
                    <span>•</span>
                    <span className="truncate max-w-[140px]">{art.mime_type}</span>
                  </div>
                </div>
                {art.is_verified && (
                  <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950/40 text-emerald-400 border border-emerald-800/40">
                    <ShieldCheck className="w-3 h-3" />
                    <span>VERIFIED</span>
                  </span>
                )}
              </div>

              {/* SHA-256 Digest */}
              <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center justify-between text-[10px] font-mono">
                <span className="text-gray-500 mr-2 shrink-0">SHA-256:</span>
                <span className="text-gray-300 truncate max-w-[220px]">{art.sha256}</span>
                <button
                  onClick={() => copySha(art.sha256, art.artifact_id)}
                  className="text-gray-500 hover:text-gray-300 ml-2"
                  title="Copy SHA-256"
                >
                  {copiedId === art.artifact_id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                </button>
              </div>

              {/* Action Bar */}
              <div className="pt-2 border-t border-amoled-border flex items-center justify-between">
                <span className="text-[10px] text-gray-500 font-mono">
                  Link expires {new Date(art.expires_at).toLocaleTimeString()}
                </span>
                <a
                  href={art.download_url}
                  download={art.filename}
                  className="px-3 py-1.5 rounded bg-electric-600 hover:bg-electric-500 text-xs font-medium text-white flex items-center space-x-1.5 transition-colors shadow-sm"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download Artifact</span>
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

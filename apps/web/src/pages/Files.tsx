import React, { useEffect, useState } from 'react';
import { FileCheck, Download, ShieldCheck, Copy, Check, Play, Pause, Volume2 } from 'lucide-react';
import { api } from '../services/api';
import { Artifact } from '../types';

export const Files: React.FC = () => {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [previewingId, setPreviewingId] = useState<string | null>(null);

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

  const getPreviewType = (mime: string, filename: string): 'video' | 'audio' | 'image' | 'pdf' | 'text' | null => {
    const m = (mime || '').toLowerCase();
    const f = (filename || '').toLowerCase();
    if (m.includes('video') || f.endsWith('.mp4') || f.endsWith('.webm') || f.endsWith('.mkv')) return 'video';
    if (m.includes('audio') || f.endsWith('.mp3') || f.endsWith('.m4a') || f.endsWith('.wav') || f.endsWith('.ogg') || f.endsWith('.flac')) return 'audio';
    if (m.startsWith('image/') || f.endsWith('.png') || f.endsWith('.jpg') || f.endsWith('.jpeg') || f.endsWith('.webp') || f.endsWith('.gif') || f.endsWith('.svg')) return 'image';
    if (m === 'application/pdf' || f.endsWith('.pdf')) return 'pdf';
    if (m.startsWith('text/') || m === 'application/json' || m === 'application/xml' || f.endsWith('.txt') || f.endsWith('.md') || f.endsWith('.json') || f.endsWith('.csv')) return 'text';
    return null;
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
              className="p-4 rounded-xl border border-amoled-border bg-amoled-card/60 hover:border-amoled-border/80 transition-all space-y-3 shadow-lg overflow-hidden flex flex-col justify-between"
            >
              <div className="flex items-start justify-between gap-3 min-w-0">
                <div className="space-y-1 min-w-0 flex-1">
                  <h3 className="text-xs font-semibold text-gray-200 truncate block" title={art.filename}>{art.filename}</h3>
                  <div className="flex items-center space-x-2 text-[10px] text-gray-500 font-mono">
                    <span className="font-semibold text-gray-400">{(art.size_bytes / 1024 / 1024).toFixed(2)} MB</span>
                    <span>•</span>
                    <span className="truncate max-w-[140px]">{art.mime_type}</span>
                  </div>
                </div>
                {art.is_verified && (
                  <span className="shrink-0 inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950/40 text-emerald-400 border border-emerald-800/40">
                    <ShieldCheck className="w-3 h-3 shrink-0" />
                    <span>VERIFIED</span>
                  </span>
                )}
              </div>

              {/* SHA-256 Digest */}
              <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center justify-between text-[10px] font-mono gap-2 min-w-0">
                <span className="text-gray-500 shrink-0">SHA-256:</span>
                <span className="text-gray-300 truncate font-mono text-[10px] flex-1 min-w-0 select-all" title={art.sha256}>
                  {art.sha256}
                </span>
                <button
                  onClick={() => copySha(art.sha256, art.artifact_id)}
                  className="text-gray-500 hover:text-gray-300 shrink-0 p-1 rounded hover:bg-amoled-card"
                  title="Copy SHA-256"
                >
                  {copiedId === art.artifact_id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                </button>
              </div>

              {/* In-Browser Media & Document Preview Stream */}
              {previewingId === art.artifact_id && (
                <div className="p-2.5 rounded-lg bg-amoled-input border border-electric-500/30 animate-in fade-in duration-200">
                  {(() => {
                    const pType = getPreviewType(art.mime_type, art.filename);
                    if (pType === 'video') {
                      return (
                        <div className="space-y-2">
                          <video
                            controls
                            autoPlay
                            playsInline
                            className="w-full max-h-56 rounded bg-black object-contain border border-amoled-border shadow-inner"
                            src={art.preview_url || art.download_url}
                          >
                            Your browser does not support video playback.
                          </video>
                          {art.contact_sheet_url && (
                            <div className="pt-2 border-t border-amoled-border/60">
                              <p className="text-[10px] text-gray-400 font-mono mb-1.5 flex items-center space-x-1">
                                <span>2x2 Verified Video Scrub Contact Sheet:</span>
                              </p>
                              <img
                                src={art.contact_sheet_url}
                                alt="2x2 Video Keyframe Contact Sheet"
                                className="w-full rounded border border-amoled-border object-cover shadow-sm"
                              />
                            </div>
                          )}
                        </div>
                      );
                    }
                    if (pType === 'audio') {
                      return (
                        <div className="flex flex-col space-y-1.5 py-1">
                          <div className="flex items-center space-x-2 text-[11px] text-electric-400 font-mono">
                            <Volume2 className="w-3.5 h-3.5" />
                            <span>Streaming Audio Preview</span>
                          </div>
                          <audio controls autoPlay className="w-full h-8" src={art.preview_url || art.download_url}>
                            Your browser does not support audio playback.
                          </audio>
                        </div>
                      );
                    }
                    if (pType === 'image') {
                      return (
                        <div className="flex justify-center p-1 bg-black/40 rounded border border-amoled-border">
                          <img
                            src={art.preview_url || art.download_url}
                            alt={art.filename}
                            className="max-h-60 max-w-full object-contain rounded"
                          />
                        </div>
                      );
                    }
                    if (pType === 'pdf') {
                      return (
                        <iframe
                          src={art.preview_url || art.download_url}
                          title={art.filename}
                          className="w-full h-72 rounded bg-white border border-amoled-border shadow-inner"
                        />
                      );
                    }
                    if (pType === 'text') {
                      return (
                        <iframe
                          src={art.preview_url || art.download_url}
                          title={art.filename}
                          className="w-full h-48 rounded bg-amoled-input p-2 font-mono text-xs text-gray-200 border border-amoled-border"
                        />
                      );
                    }
                    return (
                      <p className="text-[11px] text-gray-400 font-mono">Preview not available for this MIME type.</p>
                    );
                  })()}
                </div>
              )}

              {/* Action Bar */}
              <div className="pt-2 border-t border-amoled-border flex items-center justify-between gap-2">
                <div className="flex items-center space-x-2 min-w-0">
                  <span className="text-[10px] text-gray-500 font-mono truncate">
                    Expires {new Date(art.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  {getPreviewType(art.mime_type, art.filename) && (
                    <button
                      onClick={() => setPreviewingId(previewingId === art.artifact_id ? null : art.artifact_id)}
                      className="px-2 py-1 rounded bg-amoled-input hover:bg-amoled-hover border border-amoled-border text-[10px] text-gray-300 hover:text-white flex items-center space-x-1 transition-colors"
                    >
                      {previewingId === art.artifact_id ? (
                        <>
                          <Pause className="w-3 h-3 text-amber-400" />
                          <span>Close</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-3 h-3 text-electric-400" />
                          <span>Preview</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
                <a
                  href={art.download_url}
                  download={art.filename}
                  className="px-3 py-1.5 rounded bg-electric-600 hover:bg-electric-500 text-xs font-medium text-white flex items-center space-x-1.5 transition-colors shadow-sm shrink-0"
                >
                  <Download className="w-3.5 h-3.5 shrink-0" />
                  <span>Download</span>
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

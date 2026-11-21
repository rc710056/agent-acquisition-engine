import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Terminal, Copy, Check, Globe, Sparkles, CheckCircle2 } from 'lucide-react';
import { api } from '../services/api';
import { AgentConnection } from '../types';

export const Connections: React.FC = () => {
  const [connections, setConnections] = useState<AgentConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentName, setAgentName] = useState('');
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'stdio' | 'sse'>('stdio');

  const fetchConnections = async () => {
    try {
      const data = await api.listConnections();
      setConnections(data);
    } catch (err) {
      console.error('Failed to load connections', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConnections();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentName.trim()) return;
    setCreating(true);

    try {
      const res = await api.createConnection(agentName.trim());
      setNewKey(res.api_key || null);
      setAgentName('');
      await fetchConnections();
    } catch (err) {
      console.error('Create connection failed', err);
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await api.revokeConnection(id);
      await fetchConnections();
    } catch (err) {
      console.error('Revoke failed', err);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(label);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000';

  const stdioConfig = `{
  "mcpServers": {
    "acquisition-engine": {
      "command": "python",
      "args": ["-m", "services.mcp_server.server"],
      "env": {
        "AAE_API_KEY": "${newKey || '<YOUR_GENERATED_API_KEY>'}"
      }
    }
  }
}`;

  const sseConfig = `{
  "mcpServers": {
    "acquisition-engine": {
      "url": "${origin}/mcp/sse",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer ${newKey || '<YOUR_GENERATED_API_KEY>'}"
      }
    }
  }
}`;

  const promptExamples = [
    {
      title: "Full HD Video with Audio",
      prompt: "Download this video in best quality with synchronized audio and verify the file: https://youtu.be/aqz-KE-bpKQ"
    },
    {
      title: "Audio-Only Track (For Transcription)",
      prompt: "Extract only the audio track as an M4A from this conference lecture: https://youtu.be/kX7MlVtU9AA"
    },
    {
      title: "Social Media / Pinterest Post",
      prompt: "Inspect this Pinterest pin and acquire the highest-resolution MP4 video: https://pin.it/zRhGMggGP"
    },
    {
      title: "Multi-Image Photo Gallery",
      prompt: "Download all images from this album as a complete .zip archive: https://imgur.com/gallery/example123"
    },
    {
      title: "Direct Document & PDF",
      prompt: "Acquire this research whitepaper, verify its SHA-256 checksum, and give me the secure download link: https://example.com/spec.pdf"
    }
  ];

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Agent Connections & MCP Configuration</h2>
        <p className="text-xs text-gray-400 mt-1">
          Connect compatible autonomous AI agents directly to the Acquisition Engine via Model Context Protocol (MCP stdio or SSE).
        </p>
      </div>

      {/* 100% Working Supported Agents Banner */}
      <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-950/20 shadow-md">
        <div className="flex items-center space-x-2 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-2 font-mono">
          <CheckCircle2 className="w-4 h-4" />
          <span>100% Compatible Verified AI Agents & Clients</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-gray-300">
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>Claude Desktop</strong> (Anthropic)</span>
          </div>
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>Cursor IDE</strong> (Composer)</span>
          </div>
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>Windsurf IDE</strong> (Codeium Cascade)</span>
          </div>
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>VS Code</strong> (Cline / Roo-Code)</span>
          </div>
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>OpenAI Operator</strong> (ChatGPT)</span>
          </div>
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>Claude Code CLI</strong></span>
          </div>
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>Goose CLI</strong> (Block)</span>
          </div>
          <div className="p-2 rounded bg-amoled-input/80 border border-amoled-border flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span><strong>LangChain / CrewAI</strong></span>
          </div>
        </div>
      </div>

      {/* MCP Configuration Tabs */}
      <div className="p-5 rounded-xl border border-electric-500/30 bg-amoled-card/80 space-y-4 shadow-lg">
        <div className="flex items-center justify-between border-b border-amoled-border pb-3">
          <div className="flex items-center space-x-2 text-electric-400 font-mono text-xs font-semibold">
            <Terminal className="w-4 h-4" />
            <span>MCP PROTOCOL CONFIGURATION</span>
          </div>
          <div className="flex space-x-1.5 bg-amoled-input p-1 rounded-lg border border-amoled-border">
            <button
              onClick={() => setActiveTab('stdio')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                activeTab === 'stdio' ? 'bg-electric-600 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Desktop & IDEs (stdio)
            </button>
            <button
              onClick={() => setActiveTab('sse')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                activeTab === 'sse' ? 'bg-electric-600 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Remote & Web Agents (SSE HTTP)
            </button>
          </div>
        </div>

        {activeTab === 'stdio' ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-gray-400">
              <span>Paste into <code>claude_desktop_config.json</code>, <code>.cursor/mcp.json</code>, or Cline MCP settings:</span>
              <button
                onClick={() => copyToClipboard(stdioConfig, 'stdio')}
                className="flex items-center space-x-1 px-2.5 py-1 rounded bg-amoled-input border border-amoled-border text-xs text-electric-300 hover:text-white transition-colors"
              >
                {copiedKey === 'stdio' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedKey === 'stdio' ? 'Copied JSON!' : 'Copy Config'}</span>
              </button>
            </div>
            <pre className="p-3.5 rounded-lg bg-amoled-input border border-amoled-border text-xs font-mono text-emerald-300 overflow-x-auto leading-relaxed">
              {stdioConfig}
            </pre>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-gray-400">
              <span>Use this endpoint URL in Cursor, Windsurf, LangChain, or remote agent frameworks:</span>
              <button
                onClick={() => copyToClipboard(sseConfig, 'sse')}
                className="flex items-center space-x-1 px-2.5 py-1 rounded bg-amoled-input border border-amoled-border text-xs text-electric-300 hover:text-white transition-colors"
              >
                {copiedKey === 'sse' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedKey === 'sse' ? 'Copied JSON!' : 'Copy Config'}</span>
              </button>
            </div>
            <pre className="p-3.5 rounded-lg bg-amoled-input border border-amoled-border text-xs font-mono text-cyan-300 overflow-x-auto leading-relaxed">
              {sseConfig}
            </pre>
            <div className="p-2.5 rounded bg-amoled-input/60 border border-amoled-border text-[11px] text-gray-300 flex items-center space-x-2">
              <Globe className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>Direct SSE Streaming URL: <code className="text-cyan-300 font-mono font-semibold">http://127.0.0.1:8000/mcp/sse</code></span>
            </div>
          </div>
        )}
      </div>

      {/* Direct User Commands Guide */}
      <div className="p-5 rounded-xl border border-amoled-border bg-amoled-card/60 space-y-3 shadow-lg">
        <div className="flex items-center space-x-2 text-yellow-400 font-mono text-xs font-semibold">
          <Sparkles className="w-4 h-4" />
          <span>EXAMPLE DIRECT USER PROMPTS (COMMANDS YOU CAN GIVE TO YOUR AGENT)</span>
        </div>
        <p className="text-xs text-gray-400">
          Once your agent is connected, you don't need to visit this dashboard. Just speak directly to your agent:
        </p>
        <div className="space-y-2 pt-1">
          {promptExamples.map((item, idx) => (
            <div key={idx} className="p-3 rounded-lg bg-amoled-input border border-amoled-border flex items-center justify-between gap-3 hover:border-electric-500/50 transition-colors">
              <div className="space-y-0.5 min-w-0">
                <span className="text-[11px] font-semibold text-gray-300 font-mono block">{item.title}</span>
                <p className="text-xs text-electric-300 font-mono truncate">{item.prompt}</p>
              </div>
              <button
                onClick={() => copyToClipboard(item.prompt, `prompt_${idx}`)}
                className="px-2.5 py-1 rounded bg-amoled-card border border-amoled-border text-[11px] text-gray-400 hover:text-white flex items-center space-x-1 shrink-0"
                title="Copy prompt to clipboard"
              >
                {copiedKey === `prompt_${idx}` ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                <span>{copiedKey === `prompt_${idx}` ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Token Generation Box */}
      <div className="p-5 rounded-xl border border-amoled-border bg-amoled-card/60 space-y-4 shadow-lg">
        <h3 className="text-xs font-semibold text-gray-200 uppercase tracking-wider font-mono">Provision New Agent Identity Token</h3>
        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            type="text"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            placeholder="Agent Identifier (e.g. Claude-Desktop-Agent-1)"
            className="flex-1 bg-amoled-input border border-amoled-border text-xs text-gray-100 rounded-md px-3 py-2 focus:outline-none focus:border-electric-500"
            required
          />
          <button
            type="submit"
            disabled={creating || !agentName.trim()}
            className="px-3.5 py-2 rounded-md bg-electric-600 hover:bg-electric-500 disabled:opacity-50 text-xs font-medium text-white flex items-center space-x-1.5 transition-colors shrink-0"
          >
            <Plus className="w-4 h-4" />
            <span>Generate Token</span>
          </button>
        </form>

        {newKey && (
          <div className="p-3.5 rounded-lg bg-emerald-950/30 border border-emerald-800/40 text-xs space-y-1.5">
            <div className="flex items-center justify-between text-emerald-400 font-medium">
              <span>Agent API Key Generated (Copy now, will not be shown again):</span>
              <button
                onClick={() => copyToClipboard(newKey, 'newkey')}
                className="flex items-center space-x-1 text-emerald-300 hover:text-white"
              >
                {copiedKey === 'newkey' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedKey === 'newkey' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <code className="block p-2 rounded bg-amoled-input font-mono text-[11px] text-gray-200 break-all border border-amoled-border">
              {newKey}
            </code>
          </div>
        )}
      </div>

      {/* Active Agent Connections */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider font-mono">Registered Agent Tokens</h3>
        {loading ? (
          <div className="p-8 text-center text-xs text-gray-500 font-mono">Loading agent identities...</div>
        ) : connections.length === 0 ? (
          <div className="p-8 text-center rounded-xl border border-dashed border-amoled-border bg-amoled-card/20 text-xs text-gray-500">
            No agent credentials provisioned yet.
          </div>
        ) : (
          <div className="rounded-xl border border-amoled-border bg-amoled-card/60 divide-y divide-amoled-border/60 overflow-hidden shadow-lg">
            {connections.map((c) => (
              <div key={c.id} className="p-4 flex items-center justify-between hover:bg-amoled-hover/30 transition-colors">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-xs text-gray-200">{c.agent_name}</span>
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-amoled-input text-gray-400 border border-amoled-border">
                      {c.permissions.join(', ')}
                    </span>
                  </div>
                  <p className="text-[10px] text-gray-500 font-mono">
                    ID: {c.id} • Created: {new Date(c.created_at).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={() => handleRevoke(c.id)}
                  className="p-1.5 rounded hover:bg-red-950/40 text-gray-500 hover:text-red-400 transition-colors"
                  title="Revoke Token"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

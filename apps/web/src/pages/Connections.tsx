import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Terminal, Copy, Check } from 'lucide-react';
import { api } from '../services/api';
import { AgentConnection } from '../types';

export const Connections: React.FC = () => {
  const [connections, setConnections] = useState<AgentConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentName, setAgentName] = useState('');
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);

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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Agent Connections & MCP Endpoint</h2>
        <p className="text-xs text-gray-400 mt-1">
          Connect external AI agents (Claude Code, OpenAI agents, Antigravity) to the acquisition engine via Model Context Protocol.
        </p>
      </div>

      {/* MCP Integration Guide Card */}
      <div className="p-5 rounded-xl border border-electric-500/30 bg-amoled-card/80 space-y-3 shadow-lg">
        <div className="flex items-center space-x-2 text-electric-400 font-mono text-xs font-semibold">
          <Terminal className="w-4 h-4" />
          <span>MCP CONFIGURATION (claude_desktop_config.json / mcp.json)</span>
        </div>
        <pre className="p-3 rounded-lg bg-amoled-input border border-amoled-border text-xs font-mono text-gray-300 overflow-x-auto leading-relaxed">
{`{
  "mcpServers": {
    "agent-acquisition-engine": {
      "command": "python",
      "args": ["-m", "services.mcp_server.server"],
      "env": {
        "DATABASE_URL": "sqlite+aiosqlite:///./storage/aae.db"
      }
    }
  }
}`}
        </pre>
        <p className="text-[11px] text-gray-400">
          Once configured, compatible agents will automatically see all 7 acquisition tools: <code className="text-electric-400">inspect_source</code>, <code className="text-electric-400">list_formats</code>, <code className="text-electric-400">start_acquisition</code>, etc.
        </p>
      </div>

      {/* Token Generation Box */}
      <div className="p-5 rounded-xl border border-amoled-border bg-amoled-card/60 space-y-4 shadow-lg">
        <h3 className="text-xs font-semibold text-gray-200 uppercase tracking-wider font-mono">Provision New Agent Identity</h3>
        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            type="text"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            placeholder="Agent Identifier (e.g. Claude-DeepResearch-Agent-1)"
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
                onClick={() => copyToClipboard(newKey)}
                className="flex items-center space-x-1 text-emerald-300 hover:text-white"
              >
                {copiedKey ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedKey ? 'Copied' : 'Copy'}</span>
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

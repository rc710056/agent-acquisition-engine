import React from 'react';
import {
  ShieldCheck,
  Database,
  Server,
  Cpu,
  Sliders,
  CheckCircle2
} from 'lucide-react';

export const Settings: React.FC = () => {
  const mcpTools = [
    { name: 'inspect_source', desc: 'Inspects a target URL, checks SSRF firewalls, and retrieves media metadata without downloading' },
    { name: 'list_formats', desc: 'Discovers available formats, stream codecs, and resolutions with smart audio-video recommendations' },
    { name: 'preflight_acquisition', desc: 'Evaluates file size, storage budgets, cached duplicates, and human approval prerequisites' },
    { name: 'request_approval', desc: 'Registers a human-in-the-loop approval request when preflight indicates approval is required' },
    { name: 'start_acquisition', desc: 'Submits acquisition task to the engine queue, returns Job ID for telemetry tracking' },
    { name: 'get_job_status', desc: 'Queries real-time job progress, current operation, transferred bytes, and completion state' },
    { name: 'get_artifact', desc: 'Retrieves verified artifact metadata, SHA-256 checksum, and a secure expiring download URL' },
    { name: 'get_user_dashboard_link', desc: 'Generates or retrieves unique permanent personal dashboard link for live monitoring and approvals' }
  ];

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-12">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Engine Settings & Policies</h2>
        <p className="text-xs text-gray-400 mt-1">
          Review general system limits, backend API configuration, and MCP tool servers for autonomous AI agents.
        </p>
      </div>

      <div className="rounded-xl border border-amoled-border bg-amoled-card/60 divide-y divide-amoled-border overflow-hidden shadow-xl">
        {/* General Settings */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-gray-200">
            <Sliders className="w-4 h-4 text-electric-400" />
            <span>GENERAL ENGINE SETTINGS & LIMITS</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Max File Size</span>
              <p className="mt-1 font-mono text-gray-200">500 MB (524,288,000 bytes)</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Default Timeout</span>
              <p className="mt-1 font-mono text-gray-200">300 seconds (5 minutes)</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Worker Concurrency</span>
              <p className="mt-1 font-mono text-emerald-400">4 Parallel Jobs</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Approval Threshold</span>
              <p className="mt-1 font-mono text-amber-400">&gt; 50 MB (Requires Gate Approval)</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Max Retries per Job</span>
              <p className="mt-1 font-mono text-gray-200">3 attempts (Exponential backoff 2.0x)</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Signed Link TTL</span>
              <p className="mt-1 font-mono text-gray-200">3,600 seconds (1 hour)</p>
            </div>
          </div>
        </div>

        {/* API Config Section */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-gray-200">
            <Server className="w-4 h-4 text-electric-400" />
            <span>BACKEND API CONFIGURATION</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">API Base URL</span>
              <p className="mt-1 font-mono text-electric-400">http://127.0.0.1:8000</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Health & Telemetry Endpoint</span>
              <p className="mt-1 font-mono text-gray-200">/api/v1/health</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Environment</span>
              <div className="mt-1 flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="font-mono text-emerald-400 uppercase text-[11px]">Development (Active)</span>
              </div>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">CORS Allowed Origins</span>
              <p className="mt-1 font-mono text-gray-200">http://localhost:5173, http://127.0.0.1:5173</p>
            </div>
          </div>
        </div>

        {/* MCP Tool Servers Section */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-gray-200">
            <Cpu className="w-4 h-4 text-electric-400" />
            <span>MCP TOOL SERVERS (MODEL CONTEXT PROTOCOL)</span>
          </div>
          <p className="text-[11px] text-gray-400 leading-relaxed">
            Autonomous AI agents interface directly with the engine through 8 registered MCP tools over Server-Sent Events (SSE) or Stdio transports.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Remote SSE Transport URL</span>
              <p className="mt-1 font-mono text-electric-400">http://127.0.0.1:8000/mcp/sse</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Local Stdio Server Module</span>
              <p className="mt-1 font-mono text-gray-200">python -m services.mcp_server.server</p>
            </div>
          </div>

          <div className="space-y-2 pt-2">
            <span className="text-[10px] uppercase font-mono text-gray-500">Registered MCP Protocol Tools (8)</span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {mcpTools.map((t) => (
                <div key={t.name} className="p-2.5 rounded-lg bg-amoled-input/50 border border-amoled-border text-xs flex flex-col justify-between">
                  <div className="flex items-center space-x-1.5 font-mono text-emerald-400 font-semibold text-[11px]">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>{t.name}</span>
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1 leading-normal">{t.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Security & Firewall Section */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-gray-200">
            <ShieldCheck className="w-4 h-4 text-electric-400" />
            <span>SECURITY & FIREWALL POLICIES</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">SSRF Protection</span>
              <p className="mt-1 font-medium text-emerald-400">ENABLED (Blocking RFC-1918, Link-Local & Cloud Metadata)</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">URL Scheme Restriction</span>
              <p className="mt-1 font-mono text-gray-200">Strictly http, https, and magnet URIs only</p>
            </div>
          </div>
        </div>

        {/* Database & Storage Section */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-gray-200">
            <Database className="w-4 h-4 text-electric-400" />
            <span>DATABASE & ARTIFACT VAULT STORAGE</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Database ORM URL</span>
              <p className="mt-1 font-mono text-gray-300">sqlite+aiosqlite:///./storage/aae.db</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Artifact Vault Directory</span>
              <p className="mt-1 font-mono text-gray-300">./storage/artifacts</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
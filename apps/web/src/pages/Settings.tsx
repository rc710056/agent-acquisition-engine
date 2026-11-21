import React from 'react';
import { ShieldCheck, Database } from 'lucide-react';

export const Settings: React.FC = () => {
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Engine Settings & Policies</h2>
        <p className="text-xs text-gray-400 mt-1">
          Review system limits, SSRF network filters, and security preferences.
        </p>
      </div>

      <div className="rounded-xl border border-amoled-border bg-amoled-card/60 divide-y divide-amoled-border overflow-hidden shadow-xl">
        {/* Security Section */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-gray-200">
            <ShieldCheck className="w-4 h-4 text-electric-400" />
            <span>SECURITY POLICIES</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">SSRF Protection</span>
              <p className="mt-1 font-medium text-emerald-400">ENABLED (Blocking RFC-1918 & Metadata)</p>
            </div>
            <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border">
              <span className="text-gray-500 text-[10px] uppercase font-mono">Signed Link Expiration (TTL)</span>
              <p className="mt-1 font-mono text-gray-200">3,600 seconds (1 hour)</p>
            </div>
          </div>
        </div>

        {/* Database Section */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-gray-200">
            <Database className="w-4 h-4 text-electric-400" />
            <span>DATABASE ORM</span>
          </div>
          <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border text-xs">
            <span className="text-gray-500 text-[10px] uppercase font-mono">Database URL</span>
            <p className="mt-1 font-mono text-gray-300">sqlite+aiosqlite:///./storage/aae.db</p>
            <p className="mt-1 text-[11px] text-gray-500">PostgreSQL is supported for production container deployments via DATABASE_URL.</p>
          </div>
        </div>
      </div>
    </div>
  );
};

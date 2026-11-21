import React, { useState } from 'react';
import {
  Layers,
  Activity,
  FileCheck,
  Cpu,
  Radio,
  Settings,
  ShieldCheck,
  Sparkles,
  Link2,
  Check,
  User,
  PlusCircle
} from 'lucide-react';
import { UserProfile } from '../types';

interface NavigationProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  systemStatus: string;
  userProfile?: UserProfile | null;
  onSwitchWorkspace?: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  setActiveTab,
  systemStatus,
  userProfile,
  onSwitchWorkspace
}) => {
  const [copiedLink, setCopiedLink] = useState(false);

  const navItems = [
    { id: 'workspace', label: 'Workspace', icon: Layers },
    { id: 'jobs', label: 'Jobs', icon: Activity },
    { id: 'files', label: 'Files & Vault', icon: FileCheck },
    { id: 'approvals', label: 'Approvals Gate', icon: ShieldCheck },
    { id: 'connections', label: 'Agent Connections', icon: Cpu },
    { id: 'providers', label: 'Providers', icon: Radio },
    { id: 'how-it-works', label: 'How Stuff Works', icon: Sparkles },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  const handleCopyPersonalLink = () => {
    if (!userProfile?.dashboard_url) return;
    navigator.clipboard.writeText(userProfile.dashboard_url);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  return (
    <aside className="w-64 border-r border-amoled-border bg-amoled-card/40 flex flex-col justify-between shrink-0 h-screen sticky top-0">
      <div className="flex flex-col h-full overflow-hidden">
        {/* Header Branding */}
        <div className="p-6 border-b border-amoled-border flex items-center space-x-3 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-electric-600/20 border border-electric-500/40 flex items-center justify-center text-electric-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-wide text-gray-100">ACQUISITION ENGINE</h1>
            <p className="text-[10px] text-gray-400 tracking-wider">MCP INFRASTRUCTURE</p>
          </div>
        </div>

        {/* User Identity / Personal Link Widget */}
        {userProfile && (
          <div className="p-4 border-b border-amoled-border bg-amoled-input/30 shrink-0 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2 min-w-0">
                <div className="w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0">
                  <User className="w-3 h-3" />
                </div>
                <div className="min-w-0">
                  <div className="text-[11px] font-medium text-gray-200 truncate">
                    {userProfile.email.split('@')[0]}
                  </div>
                  <div className="text-[9px] font-mono text-emerald-400">
                    {userProfile.role.toUpperCase()}
                  </div>
                </div>
              </div>

              {onSwitchWorkspace && (
                <button
                  onClick={onSwitchWorkspace}
                  title="Switch workspace / Enter new token"
                  className="text-gray-400 hover:text-gray-200 p-1 rounded hover:bg-amoled-hover transition-colors"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <button
              onClick={handleCopyPersonalLink}
              className="w-full flex items-center justify-center space-x-1.5 px-2.5 py-1.5 rounded-md bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-900/40 text-[10px] font-mono transition-all"
            >
              {copiedLink ? <Check className="w-3 h-3 text-emerald-400" /> : <Link2 className="w-3 h-3" />}
              <span>{copiedLink ? 'Link Copied!' : 'Copy Permanent Link'}</span>
            </button>
          </div>
        )}

        {/* Navigation Items */}
        <nav className="p-4 space-y-1 overflow-y-auto flex-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            const isHighlight = item.id === 'how-it-works';
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center space-x-3 px-3 py-2 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-electric-600/20 text-electric-400 border border-electric-500/30 shadow-[0_0_15px_rgba(59,130,246,0.15)]'
                    : isHighlight
                    ? 'text-electric-300 hover:text-electric-200 hover:bg-electric-950/30 border border-electric-500/20'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-amoled-hover'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-electric-400' : isHighlight ? 'text-electric-300' : 'text-gray-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* System Status Footer */}
      <div className="p-4 border-t border-amoled-border shrink-0">
        <div className="p-3 rounded-lg bg-amoled-input border border-amoled-border flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2">
            <span className={`w-2 h-2 rounded-full ${systemStatus === 'healthy' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
            <span className="text-gray-300 font-mono text-[11px]">ENGINE CORE</span>
          </div>
          <span className="text-gray-400 text-[10px] font-mono">v0.1.0</span>
        </div>
      </div>
    </aside>
  );
};

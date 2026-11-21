import React from 'react';
import {
  Layers,
  Activity,
  FileCheck,
  Cpu,
  Radio,
  Settings,
  ShieldCheck
} from 'lucide-react';

interface NavigationProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  systemStatus: string;
}

export const Navigation: React.FC<NavigationProps> = ({ activeTab, setActiveTab, systemStatus }) => {
  const navItems = [
    { id: 'workspace', label: 'Workspace', icon: Layers },
    { id: 'jobs', label: 'Jobs', icon: Activity },
    { id: 'files', label: 'Files', icon: FileCheck },
    { id: 'approvals', label: 'Approvals', icon: ShieldCheck },
    { id: 'connections', label: 'Agent Connections', icon: Cpu },
    { id: 'providers', label: 'Providers', icon: Radio },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-amoled-border bg-amoled-card/40 flex flex-col justify-between shrink-0 h-screen sticky top-0">
      <div>
        <div className="p-6 border-b border-amoled-border flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-electric-600/20 border border-electric-500/40 flex items-center justify-center text-electric-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-wide text-gray-100">ACQUISITION ENGINE</h1>
            <p className="text-[10px] text-gray-400 tracking-wider">MCP INFRASTRUCTURE</p>
          </div>
        </div>

        <nav className="p-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-electric-600/20 text-electric-400 border border-electric-500/30 shadow-[0_0_15px_rgba(59,130,246,0.15)]'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-amoled-hover'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-electric-400' : 'text-gray-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      <div className="p-4 border-t border-amoled-border">
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

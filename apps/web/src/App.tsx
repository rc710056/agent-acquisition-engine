import React, { useState, useEffect } from 'react';
import { Navigation } from './components/Navigation';
import { Workspace } from './pages/Workspace';
import { Jobs } from './pages/Jobs';
import { Files } from './pages/Files';
import { Approvals } from './pages/Approvals';
import { Connections } from './pages/Connections';
import { Providers } from './pages/Providers';
import { Settings } from './pages/Settings';
import { HowItWorks } from './pages/HowItWorks';
import { api } from './services/api';
import { UserProfile } from './types';
import {
  Link2,
  Check,
  UserPlus,
  KeyRound,
  X,
  ShieldCheck
} from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('workspace');
  const [systemStatus, setSystemStatus] = useState<string>('healthy');
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [showSwitchModal, setShowSwitchModal] = useState<boolean>(false);
  const [inputToken, setInputToken] = useState<string>('');
  const [inputEmail, setInputEmail] = useState<string>('');
  const [copiedBannerLink, setCopiedBannerLink] = useState<boolean>(false);

  // Initialize and check URL parameters (?token=... & ?tab=...)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tokenParam = params.get('token') || params.get('user_key');
    const tabParam = params.get('tab');

    if (tokenParam) {
      api.setToken(tokenParam);
    }

    if (tabParam) {
      setActiveTab(tabParam);
    }

    loadUserProfile();

    api.getHealth()
      .then((data) => setSystemStatus(data.status))
      .catch(() => setSystemStatus('offline'));
  }, []);

  const loadUserProfile = async () => {
    try {
      const profile = await api.getMe();
      setUserProfile(profile);
    } catch (err) {
      console.error('Failed to load user profile, requesting fallback portal link:', err);
      // Auto-fallback or clear invalid token
      api.clearToken();
      try {
        const fallback = await api.getMe();
        setUserProfile(fallback);
      } catch (e) {
        console.error('Local fallback failed:', e);
      }
    }
  };

  const handleCreateNewUser = async () => {
    try {
      const res = await api.getPortalLink(inputEmail.trim() || undefined);
      api.setToken(res.portal_token);
      setInputEmail('');
      setShowSwitchModal(false);
      await loadUserProfile();
    } catch (err: any) {
      alert(`Failed to create workspace: ${err.message}`);
    }
  };

  const handleApplyExistingToken = async () => {
    if (!inputToken.trim()) return;
    api.setToken(inputToken.trim());
    setInputToken('');
    setShowSwitchModal(false);
    await loadUserProfile();
  };

  const handleCopyPermanentLink = () => {
    if (!userProfile?.dashboard_url) return;
    navigator.clipboard.writeText(userProfile.dashboard_url);
    setCopiedBannerLink(true);
    setTimeout(() => setCopiedBannerLink(false), 2000);
  };

  return (
    <div className="flex h-screen bg-amoled-bg text-gray-100 font-sans overflow-hidden">
      <Navigation
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        systemStatus={systemStatus}
        userProfile={userProfile}
        onSwitchWorkspace={() => setShowSwitchModal(true)}
      />

      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Personal Dashboard Banner */}
        {userProfile && (
          <header className="px-8 py-2.5 border-b border-amoled-border bg-amoled-card/60 backdrop-blur-md flex items-center justify-between shrink-0 text-xs">
            <div className="flex items-center space-x-3">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                PERSONAL WORKSPACE
              </span>
              <span className="text-gray-300 font-medium">
                {userProfile.email}
              </span>
              <span className="text-gray-500">•</span>
              <span className="text-gray-400">
                {userProfile.active_jobs_count} active downloads, {userProfile.artifacts_count} artifacts
              </span>
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={handleCopyPermanentLink}
                className="flex items-center space-x-1.5 px-3 py-1 rounded-md bg-amoled-input hover:bg-amoled-hover border border-amoled-border text-gray-300 hover:text-white transition-all font-mono text-[11px]"
              >
                {copiedBannerLink ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Link2 className="w-3.5 h-3.5 text-electric-400" />}
                <span>{copiedBannerLink ? 'Permanent Link Copied!' : 'Copy Permanent Link'}</span>
              </button>

              <button
                onClick={() => setShowSwitchModal(true)}
                className="px-2.5 py-1 rounded-md text-gray-400 hover:text-gray-200 hover:bg-amoled-hover transition-colors text-[11px]"
              >
                Switch Workspace
              </button>
            </div>
          </header>
        )}

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto p-8">
          {activeTab === 'workspace' && (
            <Workspace
              onJobCreated={() => setActiveTab('jobs')}
              onNavigateToFiles={() => setActiveTab('files')}
            />
          )}
          {activeTab === 'jobs' && <Jobs />}
          {activeTab === 'files' && <Files />}
          {activeTab === 'approvals' && <Approvals />}
          {activeTab === 'connections' && <Connections />}
          {activeTab === 'providers' && <Providers />}
          {activeTab === 'how-it-works' && (
            <HowItWorks
              userProfile={userProfile}
              onNavigateToWorkspace={() => setActiveTab('workspace')}
            />
          )}
          {activeTab === 'settings' && <Settings />}
        </main>
      </div>

      {/* Switch Workspace / Multi-User Modal */}
      {showSwitchModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl border border-amoled-border bg-amoled-card p-6 shadow-2xl space-y-6">
            <div className="flex items-center justify-between border-b border-amoled-border pb-4">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-5 h-5 text-electric-400" />
                <h3 className="text-base font-semibold text-white">Multi-User Personal Workspaces</h3>
              </div>
              <button
                onClick={() => setShowSwitchModal(false)}
                className="text-gray-400 hover:text-white p-1 rounded hover:bg-amoled-hover"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Current Active Workspace Info */}
            {userProfile && (
              <div className="p-3.5 rounded-xl bg-amoled-input border border-amoled-border space-y-1 text-xs">
                <div className="text-[10px] font-mono text-gray-400 uppercase">Current Workspace</div>
                <div className="text-white font-medium">{userProfile.email}</div>
                <div className="text-[10px] font-mono text-emerald-400 truncate">Token: {userProfile.portal_token}</div>
              </div>
            )}

            {/* Option A: Create New User Workspace */}
            <div className="space-y-3">
              <h4 className="text-xs font-semibold text-gray-200 uppercase tracking-wider flex items-center space-x-1.5">
                <UserPlus className="w-3.5 h-3.5 text-electric-400" />
                <span>Create Fresh User Workspace</span>
              </h4>
              <p className="text-[11px] text-gray-400 leading-relaxed">
                Provisions a new isolated tenant with private jobs, artifacts, and a unique permanent link.
              </p>
              <div className="flex space-x-2">
                <input
                  type="email"
                  placeholder="Optional email (e.g. alice@acme.com)"
                  value={inputEmail}
                  onChange={(e) => setInputEmail(e.target.value)}
                  className="flex-1 bg-amoled-input border border-amoled-border rounded-lg px-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-electric-500"
                />
                <button
                  onClick={handleCreateNewUser}
                  className="px-4 py-2 bg-electric-600 hover:bg-electric-500 text-white rounded-lg text-xs font-medium transition-all"
                >
                  Create
                </button>
              </div>
            </div>

            <div className="relative flex py-1 items-center">
              <div className="flex-grow border-t border-amoled-border"></div>
              <span className="flex-shrink mx-4 text-gray-500 text-[10px] uppercase font-mono">OR</span>
              <div className="flex-grow border-t border-amoled-border"></div>
            </div>

            {/* Option B: Enter Existing Token */}
            <div className="space-y-3">
              <h4 className="text-xs font-semibold text-gray-200 uppercase tracking-wider flex items-center space-x-1.5">
                <KeyRound className="w-3.5 h-3.5 text-emerald-400" />
                <span>Enter Existing Permanent Token</span>
              </h4>
              <div className="flex space-x-2">
                <input
                  type="text"
                  placeholder="Paste your aae_usr_... token"
                  value={inputToken}
                  onChange={(e) => setInputToken(e.target.value)}
                  className="flex-1 bg-amoled-input border border-amoled-border rounded-lg px-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 font-mono"
                />
                <button
                  onClick={handleApplyExistingToken}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition-all"
                >
                  Switch
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

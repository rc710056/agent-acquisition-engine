import React, { useState, useEffect } from 'react';
import { Navigation } from './components/Navigation';
import { Workspace } from './pages/Workspace';
import { Jobs } from './pages/Jobs';
import { Files } from './pages/Files';
import { Approvals } from './pages/Approvals';
import { Connections } from './pages/Connections';
import { Providers } from './pages/Providers';
import { Settings } from './pages/Settings';
import { api } from './services/api';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('workspace');
  const [systemStatus, setSystemStatus] = useState<string>('healthy');

  useEffect(() => {
    api.getHealth()
      .then((data) => setSystemStatus(data.status))
      .catch(() => setSystemStatus('offline'));
  }, []);

  return (
    <div className="flex h-screen bg-amoled-bg text-gray-100 font-sans overflow-hidden">
      <Navigation
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        systemStatus={systemStatus}
      />
      <main className="flex-1 overflow-y-auto p-8">
        {activeTab === 'workspace' && <Workspace onJobCreated={() => setActiveTab('jobs')} />}
        {activeTab === 'jobs' && <Jobs />}
        {activeTab === 'files' && <Files />}
        {activeTab === 'approvals' && <Approvals />}
        {activeTab === 'connections' && <Connections />}
        {activeTab === 'providers' && <Providers />}
        {activeTab === 'settings' && <Settings />}
      </main>
    </div>
  );
};

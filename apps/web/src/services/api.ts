import {
  SourceInspection,
  FormatOption,
  AcquisitionJob,
  Artifact,
  AgentConnection,
  ProviderInfo,
  UserProfile,
  PortalLinkResponse
} from '../types';

const BASE_URL = '/api/v1';

function getAuthHeader(): Record<string, string> {
  const token = localStorage.getItem('aae_user_token');
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = {
    ...getAuthHeader(),
    ...(options.headers || {})
  };
  return fetch(url, { ...options, headers });
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorJson = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorJson.detail || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export const api = {
  setToken(token: string) {
    localStorage.setItem('aae_user_token', token);
  },

  getToken(): string | null {
    return localStorage.getItem('aae_user_token');
  },

  clearToken() {
    localStorage.removeItem('aae_user_token');
  },

  async getHealth(): Promise<{ status: string; environment: string }> {
    const res = await authFetch('/health');
    return handleResponse(res);
  },

  async getMe(): Promise<UserProfile> {
    const res = await authFetch(`${BASE_URL}/users/me`);
    return handleResponse(res);
  },

  async getPortalLink(email?: string): Promise<PortalLinkResponse> {
    const res = await authFetch(`${BASE_URL}/users/portal-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email || null })
    });
    return handleResponse(res);
  },

  async inspectSource(url: string): Promise<SourceInspection> {
    const res = await authFetch(`${BASE_URL}/sources/inspect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    return handleResponse(res);
  },

  async listFormats(sourceId: string): Promise<FormatOption[]> {
    const res = await authFetch(`${BASE_URL}/sources/${sourceId}/formats`);
    return handleResponse(res);
  },

  async preflight(sourceId: string, formatId: string): Promise<{
    can_acquire: boolean;
    requires_approval: boolean;
    approval_reason: string | null;
    estimated_size_bytes: number | null;
  }> {
    const res = await authFetch(`${BASE_URL}/acquisitions/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_id: sourceId, format_id: formatId })
    });
    return handleResponse(res);
  },

  async createJob(sourceId: string, formatId: string, approvalId?: string, autoApprove?: boolean): Promise<AcquisitionJob> {
    const res = await authFetch(`${BASE_URL}/acquisitions/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_id: sourceId,
        format_id: formatId,
        approval_id: approvalId || null,
        execution_mode: 'cloud',
        auto_approve: !!autoApprove
      })
    });
    return handleResponse(res);
  },

  async listJobs(): Promise<AcquisitionJob[]> {
    const res = await authFetch(`${BASE_URL}/acquisitions/jobs`);
    return handleResponse(res);
  },

  async getJob(jobId: string): Promise<AcquisitionJob> {
    const res = await authFetch(`${BASE_URL}/acquisitions/jobs/${jobId}`);
    return handleResponse(res);
  },

  async cancelJob(jobId: string): Promise<AcquisitionJob> {
    const res = await authFetch(`${BASE_URL}/acquisitions/jobs/${jobId}/cancel`, {
      method: 'POST'
    });
    return handleResponse(res);
  },

  async listArtifacts(): Promise<Artifact[]> {
    const res = await authFetch(`${BASE_URL}/artifacts`);
    return handleResponse(res);
  },

  async listApprovals(): Promise<any[]> {
    const res = await authFetch(`${BASE_URL}/approvals`);
    return handleResponse(res);
  },

  async decideApproval(approvalId: string, decision: 'approved' | 'rejected'): Promise<any> {
    const res = await authFetch(`${BASE_URL}/approvals/${approvalId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision })
    });
    return handleResponse(res);
  },

  async listConnections(): Promise<AgentConnection[]> {
    const res = await authFetch(`${BASE_URL}/connections`);
    return handleResponse(res);
  },

  async createConnection(agentName: string): Promise<AgentConnection> {
    const res = await authFetch(`${BASE_URL}/connections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: agentName })
    });
    return handleResponse(res);
  },

  async revokeConnection(id: string): Promise<void> {
    const res = await authFetch(`${BASE_URL}/connections/${id}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to revoke agent connection');
  },

  async listProviders(): Promise<ProviderInfo[]> {
    const res = await authFetch(`${BASE_URL}/providers`);
    return handleResponse(res);
  }
};

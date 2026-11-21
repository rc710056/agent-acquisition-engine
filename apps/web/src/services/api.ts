import {
  SourceInspection,
  FormatOption,
  AcquisitionJob,
  Artifact,
  AgentConnection,
  ProviderInfo
} from '../types';

const BASE_URL = '/api/v1';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorJson = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorJson.detail || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export const api = {
  async getHealth(): Promise<{ status: string; environment: string }> {
    const res = await fetch('/health');
    return handleResponse(res);
  },

  async inspectSource(url: string): Promise<SourceInspection> {
    const res = await fetch(`${BASE_URL}/sources/inspect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    return handleResponse(res);
  },

  async listFormats(sourceId: string): Promise<FormatOption[]> {
    const res = await fetch(`${BASE_URL}/sources/${sourceId}/formats`);
    return handleResponse(res);
  },

  async preflight(sourceId: string, formatId: string): Promise<{
    can_acquire: boolean;
    requires_approval: boolean;
    approval_reason: string | null;
    estimated_size_bytes: number | null;
  }> {
    const res = await fetch(`${BASE_URL}/acquisitions/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_id: sourceId, format_id: formatId })
    });
    return handleResponse(res);
  },

  async createJob(sourceId: string, formatId: string, approvalId?: string): Promise<AcquisitionJob> {
    const res = await fetch(`${BASE_URL}/acquisitions/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_id: sourceId,
        format_id: formatId,
        approval_id: approvalId || null,
        execution_mode: 'cloud'
      })
    });
    return handleResponse(res);
  },

  async listJobs(): Promise<AcquisitionJob[]> {
    const res = await fetch(`${BASE_URL}/acquisitions/jobs`);
    return handleResponse(res);
  },

  async getJob(jobId: string): Promise<AcquisitionJob> {
    const res = await fetch(`${BASE_URL}/acquisitions/jobs/${jobId}`);
    return handleResponse(res);
  },

  async cancelJob(jobId: string): Promise<AcquisitionJob> {
    const res = await fetch(`${BASE_URL}/acquisitions/jobs/${jobId}/cancel`, {
      method: 'POST'
    });
    return handleResponse(res);
  },

  async listArtifacts(): Promise<Artifact[]> {
    const res = await fetch(`${BASE_URL}/artifacts`);
    return handleResponse(res);
  },

  async listConnections(): Promise<AgentConnection[]> {
    const res = await fetch(`${BASE_URL}/connections`);
    return handleResponse(res);
  },

  async createConnection(agentName: string): Promise<AgentConnection> {
    const res = await fetch(`${BASE_URL}/connections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: agentName })
    });
    return handleResponse(res);
  },

  async revokeConnection(id: string): Promise<void> {
    const res = await fetch(`${BASE_URL}/connections/${id}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to revoke agent connection');
  },

  async listProviders(): Promise<ProviderInfo[]> {
    const res = await fetch(`${BASE_URL}/providers`);
    return handleResponse(res);
  }
};

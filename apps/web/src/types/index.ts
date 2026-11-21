export interface SourceInspection {
  source_id: string;
  url: string;
  provider_id: string;
  is_permitted: boolean;
  capabilities: string[];
  mime_type: string | null;
  estimated_size_bytes: number | null;
  inspection_status: string;
  errors: string[];
}

export interface FormatOption {
  format_id: string;
  file_type: string;
  mime_type: string;
  resolution?: string | null;
  codec?: string | null;
  estimated_size_bytes?: number | null;
  quality_label: string;
}

export interface AcquisitionJob {
  job_id: string;
  state: string;
  progress_percent: number;
  bytes_transferred: number;
  total_bytes: number | null;
  current_operation: string;
  artifact_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Artifact {
  artifact_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  is_verified: boolean;
  download_url: string;
  expires_at: string;
}

export interface AgentConnection {
  id: string;
  agent_name: string;
  api_key?: string | null;
  permissions: string[];
  last_active_at?: string | null;
  created_at: string;
}

export interface ProviderInfo {
  provider_id: string;
  display_name: string;
  status: string;
  supported_schemes: string[];
  capabilities: string[];
}

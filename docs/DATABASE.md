# Database Schema & Entity Relationship

The database layer uses SQLAlchemy 2.0 async ORM supporting PostgreSQL for production and SQLite for local development and unit testing.

## Entity Relationship Overview

```
users (1) ───────────< agent_connections (N)
  │
  ├──────────────────< acquisition_requests (N)
  │                          │ (1)
  │                          ▼
  ├──────────────────< sources (N) ───────────< source_options (N)
  │                          │ (1)
  │                          ▼
  ├──────────────────< acquisition_jobs (N) ───< job_events (N)
  │                          │ (1)
  │                          ▼
  ├──────────────────< artifacts (N) ─────────< delivery_links (N)
  │
  ├──────────────────< user_approvals (N)
  │
  └──────────────────< usage_records (N)

provider_registry (Standalone lookup table)
```

## Entities Specification

### 1. `users`
- `id` (VARCHAR(36), PK)
- `email` (VARCHAR(255), UNIQUE, NOT NULL)
- `hashed_password` (VARCHAR(255), NOT NULL)
- `role` (VARCHAR(50), default 'user')
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

### 2. `agent_connections`
- `id` (VARCHAR(36), PK)
- `user_id` (VARCHAR(36), FK -> users.id)
- `agent_name` (VARCHAR(100), NOT NULL)
- `api_key_hash` (VARCHAR(128), NOT NULL, INDEX)
- `permissions` (JSON, default '["read", "acquire"]')
- `last_active_at` (TIMESTAMP)
- `created_at` (TIMESTAMP)

### 3. `sources`
- `id` (VARCHAR(36), PK)
- `url` (TEXT, NOT NULL)
- `canonical_url` (TEXT)
- `provider_id` (VARCHAR(50), NOT NULL)
- `content_type` (VARCHAR(100))
- `estimated_size_bytes` (BIGINT)
- `is_permitted` (BOOLEAN, default TRUE)
- `inspection_status` (VARCHAR(50))
- `created_at` (TIMESTAMP)

### 4. `source_options` (Available formats per source)
- `id` (VARCHAR(36), PK)
- `source_id` (VARCHAR(36), FK -> sources.id)
- `format_id` (VARCHAR(100), NOT NULL)
- `file_type` (VARCHAR(50))
- `mime_type` (VARCHAR(100))
- `resolution` (VARCHAR(50))
- `codec` (VARCHAR(50))
- `estimated_size_bytes` (BIGINT)
- `quality_label` (VARCHAR(50))

### 5. `acquisition_jobs`
- `id` (VARCHAR(36), PK)
- `user_id` (VARCHAR(36), FK -> users.id)
- `source_id` (VARCHAR(36), FK -> sources.id)
- `format_id` (VARCHAR(100), NOT NULL)
- `execution_mode` (VARCHAR(20), default 'cloud')
- `state` (VARCHAR(50), NOT NULL, INDEX) -- Enum: created, inspecting, awaiting_approval, queued, downloading, verifying, completed, failed, cancelled
- `progress_percent` (FLOAT, default 0.0)
- `bytes_transferred` (BIGINT, default 0)
- `total_bytes` (BIGINT)
- `retry_count` (INTEGER, default 0)
- `max_retries` (INTEGER, default 3)
- `error_message` (TEXT)
- `artifact_id` (VARCHAR(36), FK -> artifacts.id)
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

### 6. `job_events`
- `id` (VARCHAR(36), PK)
- `job_id` (VARCHAR(36), FK -> acquisition_jobs.id)
- `event_type` (VARCHAR(50), NOT NULL)
- `message` (TEXT, NOT NULL)
- `payload` (JSON)
- `created_at` (TIMESTAMP)

### 7. `artifacts`
- `id` (VARCHAR(36), PK)
- `user_id` (VARCHAR(36), FK -> users.id)
- `job_id` (VARCHAR(36), FK -> acquisition_jobs.id)
- `filename` (VARCHAR(255), NOT NULL)
- `mime_type` (VARCHAR(100), NOT NULL)
- `size_bytes` (BIGINT, NOT NULL)
- `sha256` (VARCHAR(64), NOT NULL, INDEX)
- `storage_path` (TEXT, NOT NULL)
- `is_verified` (BOOLEAN, default FALSE)
- `created_at` (TIMESTAMP)

### 8. `user_approvals`
- `id` (VARCHAR(36), PK)
- `user_id` (VARCHAR(36), FK -> users.id)
- `source_id` (VARCHAR(36), FK -> sources.id)
- `format_id` (VARCHAR(100))
- `status` (VARCHAR(50), default 'pending') -- pending, approved, rejected
- `reason` (TEXT)
- `estimated_size_bytes` (BIGINT)
- `decided_at` (TIMESTAMP)
- `created_at` (TIMESTAMP)

### 9. `provider_registry`
- `id` (VARCHAR(50), PK)
- `name` (VARCHAR(100), NOT NULL)
- `is_enabled` (BOOLEAN, default TRUE)
- `supported_schemes` (JSON)
- `supported_domains` (JSON)
- `version` (VARCHAR(20))
- `created_at` (TIMESTAMP)

### 10. `usage_records`
- `id` (VARCHAR(36), PK)
- `user_id` (VARCHAR(36), FK -> users.id)
- `job_id` (VARCHAR(36))
- `bytes_downloaded` (BIGINT)
- `duration_seconds` (FLOAT)
- `created_at` (TIMESTAMP)

### 11. `delivery_links`
- `id` (VARCHAR(36), PK)
- `artifact_id` (VARCHAR(36), FK -> artifacts.id)
- `token_hash` (VARCHAR(128), NOT NULL, INDEX)
- `expires_at` (TIMESTAMP, NOT NULL)
- `download_count` (INTEGER, default 0)
- `created_at` (TIMESTAMP)

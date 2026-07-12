CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE document_status AS ENUM ('pending', 'extracting', 'chunking', 'embedded', 'failed');
CREATE TYPE processing_stage AS ENUM ('upload', 'extract', 'ocr', 'chunk', 'embed');
CREATE TYPE visibility AS ENUM ('private', 'tenant', 'role');

CREATE TABLE IF NOT EXISTS tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  keycloak_subject TEXT NOT NULL,
  email TEXT NOT NULL,
  display_name TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, keycloak_subject),
  UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  uploaded_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
  source_uri TEXT NOT NULL,
  file_name TEXT NOT NULL,
  mime_type TEXT,
  content_sha256 TEXT NOT NULL,
  byte_size BIGINT NOT NULL,
  status document_status NOT NULL DEFAULT 'pending',
  visibility visibility NOT NULL DEFAULT 'tenant',
  allowed_role_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ocr_required BOOLEAN NOT NULL DEFAULT FALSE,
  extraction_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_status ON documents (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_documents_content_sha ON documents (tenant_id, content_sha256);

CREATE TABLE IF NOT EXISTS document_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  page_number INTEGER,
  section_title TEXT,
  visibility visibility NOT NULL,
  allowed_role_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ocr_used BOOLEAN NOT NULL DEFAULT FALSE,
  source_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  embedding vector(1024),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_document ON document_chunks (tenant_id, document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_rbac ON document_chunks USING GIN (allowed_role_names);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON document_chunks USING GIN (source_metadata);

CREATE TABLE IF NOT EXISTS processing_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  stage processing_stage NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs (status, stage, created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
  actor_user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  request_id TEXT,
  ip_address INET,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_time ON audit_logs (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS query_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  cached BOOLEAN NOT NULL DEFAULT FALSE,
  retrieval_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
  total_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_query_events_tenant_time ON query_events (tenant_id, created_at DESC);

INSERT INTO tenants (id, name, slug)
VALUES ('00000000-0000-4000-8000-000000000001', 'Demo Tenant', 'demo')
ON CONFLICT (slug) DO UPDATE SET
  id = EXCLUDED.id,
  name = EXCLUDED.name;

INSERT INTO roles (tenant_id, name, description) VALUES
  ('00000000-0000-4000-8000-000000000001', 'admin', 'Tenant administrator'),
  ('00000000-0000-4000-8000-000000000001', 'finance', 'Finance team member'),
  ('00000000-0000-4000-8000-000000000001', 'engineering', 'Engineering team member'),
  ('00000000-0000-4000-8000-000000000001', 'legal', 'Legal team member'),
  ('00000000-0000-4000-8000-000000000001', 'support', 'Support team member')
ON CONFLICT (tenant_id, name) DO NOTHING;

-- Demo users, keyed by the fixed Keycloak user "id" values from
-- infra/keycloak/realm-export.json, so a login through Keycloak resolves
-- straight to the matching tenant/role rows below.
INSERT INTO app_users (id, tenant_id, keycloak_subject, email, display_name) VALUES
  ('20000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'admin-demo@example.test', 'Alex Admin'),
  ('20000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000002', 'finance-demo@example.test', 'Farah Finance'),
  ('20000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000003', 'engineer-demo@example.test', 'Evan Engineer'),
  ('20000000-0000-4000-8000-000000000004', '00000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000004', 'legal-demo@example.test', 'Lena Legal'),
  ('20000000-0000-4000-8000-000000000005', '00000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000005', 'support-demo@example.test', 'Sam Support')
ON CONFLICT (tenant_id, keycloak_subject) DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM app_users u
JOIN roles r ON r.tenant_id = u.tenant_id
WHERE (u.display_name, r.name) IN (
  ('Alex Admin', 'admin'),
  ('Farah Finance', 'finance'),
  ('Evan Engineer', 'engineering'),
  ('Lena Legal', 'legal'),
  ('Sam Support', 'support')
)
ON CONFLICT (user_id, role_id) DO NOTHING;

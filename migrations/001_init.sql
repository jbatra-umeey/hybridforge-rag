BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE schema_version (version integer PRIMARY KEY, applied_at timestamptz DEFAULT now());
CREATE TABLE documents (
  tenant text NOT NULL, document_id text NOT NULL,
  version integer NOT NULL CHECK (version > 0), digest text NOT NULL,
  title text NOT NULL, source text NOT NULL, acl_groups text[] NOT NULL DEFAULT '{}',
  embedding_id text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant, document_id)
);
CREATE TABLE chunks (
  tenant text NOT NULL, document_id text NOT NULL, chunk_id text NOT NULL,
  version integer NOT NULL, title text NOT NULL, source text NOT NULL, body text NOT NULL,
  start_char integer NOT NULL, end_char integer NOT NULL,
  embedding vector(1536) NOT NULL,
  search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', title), 'A') ||
    setweight(to_tsvector('english', body), 'B')
  ) STORED,
  PRIMARY KEY (tenant, chunk_id),
  FOREIGN KEY (tenant,document_id) REFERENCES documents(tenant,document_id) ON DELETE CASCADE
);
CREATE INDEX chunks_fts ON chunks USING gin(search_vector);
CREATE INDEX chunks_document ON chunks(tenant, document_id);
CREATE INDEX documents_embedding ON documents(tenant, embedding_id);
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks FORCE ROW LEVEL SECURITY;

CREATE POLICY document_read ON documents FOR SELECT USING (
  tenant = current_setting('app.tenant',true) AND (
    current_setting('app.can_write',true) = 'true' OR cardinality(acl_groups)=0 OR
    coalesce(nullif(current_setting('app.groups',true),''),'[]')::jsonb ?| acl_groups
  )
);
CREATE POLICY document_insert ON documents FOR INSERT WITH CHECK (
  tenant = current_setting('app.tenant',true) AND current_setting('app.can_write',true)='true'
);
CREATE POLICY document_delete ON documents FOR DELETE USING (
  tenant = current_setting('app.tenant',true) AND current_setting('app.can_write',true)='true'
);
CREATE POLICY chunk_read ON chunks FOR SELECT USING (
  tenant = current_setting('app.tenant',true) AND EXISTS (
    SELECT 1 FROM documents d WHERE d.tenant=chunks.tenant AND d.document_id=chunks.document_id
  )
);
CREATE POLICY chunk_insert ON chunks FOR INSERT WITH CHECK (
  tenant = current_setting('app.tenant',true) AND current_setting('app.can_write',true)='true'
);
CREATE POLICY chunk_delete ON chunks FOR DELETE USING (
  tenant = current_setting('app.tenant',true) AND current_setting('app.can_write',true)='true'
);
INSERT INTO schema_version(version) VALUES (1);
COMMIT;


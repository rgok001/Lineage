-- 001: core tables for papers, definitions, edges, genealogies.
-- Embeddings live on definitions (pgvector). Dimension 1024 = Voyage voyage-3;
-- changing embedding model means a new migration.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE papers (
    id                  BIGSERIAL PRIMARY KEY,
    arxiv_id            TEXT UNIQUE NOT NULL,
    openalex_id         TEXT UNIQUE,
    title               TEXT NOT NULL,
    authors             JSONB NOT NULL DEFAULT '[]',
    year                INT,
    cited_by_count      INT NOT NULL DEFAULT 0,
    abstract            TEXT,
    source_format       TEXT CHECK (source_format IN ('latex', 'pdf')),
    raw_path            TEXT,   -- raw .tex/.pdf under DATA_DIR
    extracted_text_path TEXT,   -- structured text used for grounding checks
    fetched_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stage B output. Cached per paper: (paper, concept, prompt_version) is the cache key.
CREATE TABLE definitions (
    id             BIGSERIAL PRIMARY KEY,
    paper_id       BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    concept        TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    definition     TEXT NOT NULL,
    verbatim_quote TEXT NOT NULL,
    quote_verified BOOLEAN NOT NULL DEFAULT false,  -- grounding check result
    section        TEXT,
    novelty_claims JSONB NOT NULL DEFAULT '[]',
    embedding      vector(1024),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (paper_id, concept, prompt_version)
);

CREATE TABLE genealogies (
    id             BIGSERIAL PRIMARY KEY,
    concept        TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'running', 'complete', 'failed', 'aborted_spend_cap')),
    spend_usd      NUMERIC(8, 4) NOT NULL DEFAULT 0,
    -- concept-states (nodes) as JSON: [{node_id, label, year_range, definition_ids}]
    nodes          JSONB NOT NULL DEFAULT '[]',
    -- workbench audit trail: splits, merges, renames, deletes
    user_edits     JSONB NOT NULL DEFAULT '[]',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE edges (
    id              BIGSERIAL PRIMARY KEY,
    genealogy_id    BIGINT NOT NULL REFERENCES genealogies(id) ON DELETE CASCADE,
    source_node     TEXT NOT NULL,  -- node_id within genealogies.nodes
    target_node     TEXT NOT NULL,
    edge_type       TEXT NOT NULL
                    CHECK (edge_type IN ('extends', 'contests', 'narrows', 'renames', 'merges', 'migrates')),
    source_paper_id BIGINT REFERENCES papers(id),
    target_paper_id BIGINT REFERENCES papers(id),
    source_quote    TEXT NOT NULL,
    target_quote    TEXT NOT NULL,
    confidence      REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    verified        BOOLEAN NOT NULL DEFAULT false,  -- solid vs dotted "inferred"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_definitions_paper ON definitions (paper_id);
CREATE INDEX idx_edges_genealogy ON edges (genealogy_id);
CREATE INDEX idx_genealogies_concept ON genealogies (concept);

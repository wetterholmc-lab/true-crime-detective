CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE detective_chunks (
    id          serial PRIMARY KEY,
    case_id     int  NOT NULL REFERENCES detective_cases(id) ON DELETE CASCADE,
    chunk_index int  NOT NULL,
    text        text NOT NULL,
    embedding   vector(1024),
    UNIQUE (case_id, chunk_index)
);

-- HNSW index: works well at small row counts (IVFFlat requires ~100 rows/cluster)
CREATE INDEX detective_chunks_embedding_idx
    ON detective_chunks USING hnsw (embedding vector_cosine_ops);

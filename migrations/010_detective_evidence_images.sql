-- Cache for generated Victorian-era evidence illustrations.
-- Generated once per (case, evidence_id); all players share the same image.
CREATE TABLE IF NOT EXISTS detective_evidence_images (
    case_id     INTEGER  NOT NULL,
    evidence_id TEXT     NOT NULL,
    image_url   TEXT     NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (case_id, evidence_id)
);

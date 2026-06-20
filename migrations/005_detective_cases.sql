CREATE TABLE detective_cases (
    id          serial PRIMARY KEY,
    slug        text UNIQUE NOT NULL,
    title       text NOT NULL,
    court       text NOT NULL DEFAULT 'Old Bailey',
    year        int  NOT NULL,
    accused_name text NOT NULL,
    crime       text NOT NULL,
    brief       text NOT NULL,
    cast_json   jsonb NOT NULL DEFAULT '[]',
    evidence_json jsonb NOT NULL DEFAULT '[]',
    verdict     text NOT NULL CHECK (verdict IN ('guilty', 'not_guilty')),
    verdict_text   text NOT NULL,
    aftermath_text text NOT NULL,
    active      bool NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE detective_players
    ADD COLUMN IF NOT EXISTS authenticated bool NOT NULL DEFAULT false;

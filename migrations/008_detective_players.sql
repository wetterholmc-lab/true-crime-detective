CREATE TABLE detective_players (
    telegram_id         bigint PRIMARY KEY,
    cases_attempted     int NOT NULL DEFAULT 0,
    cases_correct       int NOT NULL DEFAULT 0,
    cases_wrong_verdict int NOT NULL DEFAULT 0,
    cases_wrong_person  int NOT NULL DEFAULT 0,
    cases_abandoned     int NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    last_active_at      timestamptz NOT NULL DEFAULT now()
);

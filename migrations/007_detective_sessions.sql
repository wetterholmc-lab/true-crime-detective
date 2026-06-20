CREATE TABLE detective_sessions (
    id                  serial PRIMARY KEY,
    telegram_id         bigint NOT NULL,
    case_id             int    NOT NULL REFERENCES detective_cases(id),
    status              text   NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'solved', 'abandoned')),
    clues_examined      jsonb  NOT NULL DEFAULT '[]',
    hint_count          int    NOT NULL DEFAULT 0,
    pending_accusation  bool   NOT NULL DEFAULT false,
    accusation_name     text,
    accusation_verdict  text   CHECK (accusation_verdict IN ('guilty', 'not_guilty')),
    score               text   CHECK (score IN ('correct', 'wrong_verdict', 'wrong_person')),
    started_at          timestamptz NOT NULL DEFAULT now(),
    last_active_at      timestamptz NOT NULL DEFAULT now(),
    closed_at           timestamptz
);

CREATE INDEX detective_sessions_telegram_id_idx ON detective_sessions (telegram_id);
CREATE INDEX detective_sessions_stale_idx
    ON detective_sessions (last_active_at)
    WHERE status = 'active';

CREATE SCHEMA IF NOT EXISTS support_app;

CREATE TABLE IF NOT EXISTS support_app.tickets (
    ticket_id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    category TEXT NOT NULL DEFAULT 'general',
    created_by TEXT NOT NULL CHECK (length(trim(created_by)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seed_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS support_app.ticket_messages (
    message_id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES support_app.tickets(ticket_id) ON DELETE CASCADE,
    message_text TEXT NOT NULL CHECK (length(trim(message_text)) > 0),
    author TEXT NOT NULL CHECK (length(trim(author)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seed_key TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_app.tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON support_app.tickets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id_created_at
    ON support_app.ticket_messages(ticket_id, created_at ASC);

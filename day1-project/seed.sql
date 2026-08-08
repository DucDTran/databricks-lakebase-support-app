INSERT INTO support_app.tickets (title, description, status, priority, category, created_by, seed_key)
VALUES
    (
        'Cannot access internal dashboard',
        'User receives an authorization error after signing in with SSO.',
        'open',
        'high',
        'access',
        'maya@company.com',
        'ticket-dashboard-access'
    ),
    (
        'Customer data sync is delayed',
        'Daily customer records have not appeared in the support workspace.',
        'in_progress',
        'urgent',
        'data',
        'liam@company.com',
        'ticket-data-sync'
    ),
    (
        'Billing export request',
        'Finance needs a refreshed CSV export for last month invoices.',
        'resolved',
        'medium',
        'billing',
        'nora@company.com',
        'ticket-billing-export'
    )
ON CONFLICT (seed_key) DO NOTHING;

WITH target_ticket AS (
    SELECT ticket_id FROM support_app.tickets WHERE seed_key = 'ticket-dashboard-access'
)
INSERT INTO support_app.ticket_messages (ticket_id, message_text, author, seed_key)
SELECT ticket_id, message_text, author, seed_key
FROM target_ticket
CROSS JOIN (
    VALUES
        ('I can sign in, but the dashboard says I do not have permission.', 'maya@company.com', 'msg-dashboard-1'),
        ('Thanks, checking the workspace group assignments now.', 'sam.support@company.com', 'msg-dashboard-2')
) AS messages(message_text, author, seed_key)
ON CONFLICT (seed_key) DO NOTHING;

WITH target_ticket AS (
    SELECT ticket_id FROM support_app.tickets WHERE seed_key = 'ticket-data-sync'
)
INSERT INTO support_app.ticket_messages (ticket_id, message_text, author, seed_key)
SELECT ticket_id, message_text, author, seed_key
FROM target_ticket
CROSS JOIN (
    VALUES
        ('The expected customer records are missing from this morning.', 'liam@company.com', 'msg-sync-1'),
        ('Pipeline logs show the source API throttled during the final page.', 'pri.support@company.com', 'msg-sync-2')
) AS messages(message_text, author, seed_key)
ON CONFLICT (seed_key) DO NOTHING;

WITH target_ticket AS (
    SELECT ticket_id FROM support_app.tickets WHERE seed_key = 'ticket-billing-export'
)
INSERT INTO support_app.ticket_messages (ticket_id, message_text, author, seed_key)
SELECT ticket_id, message_text, author, seed_key
FROM target_ticket
CROSS JOIN (
    VALUES
        ('Can you regenerate the invoice CSV with the corrected tax codes?', 'nora@company.com', 'msg-billing-1'),
        ('The export has been regenerated and shared with Finance.', 'sam.support@company.com', 'msg-billing-2')
) AS messages(message_text, author, seed_key)
ON CONFLICT (seed_key) DO NOTHING;

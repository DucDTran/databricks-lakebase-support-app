# Day 1 Evidence Addendum

## App Access

Databricks App URL:

[https://lakebase-support-desk-7474655808298242.aws.databricksapps.com/#tickets](https://lakebase-support-desk-7474655808298242.aws.databricksapps.com/#tickets)

If the app is not accessible to graders, grant access to the Databricks workspace or add the instructor to the app permissions before resubmitting.

## Source Repository

Public repository URL:

[https://github.com/DucDTran/databricks-lakebase-support-app.git](https://github.com/DucDTran/databricks-lakebase-support-app.git)

The repository is intended to be public for grader access. If it is changed to private later, invite the graders or provide a read-only access link.

Commands used to publish from this folder:

```bash
cd /Users/dwctran/Personal/databricks-bootcamp
git init
git add app.yaml server.py schema.sql seed.sql src index.html package.json package-lock.json requirements.txt tailwind.config.js postcss.config.js tsconfig.json vite.config.ts README.md docs submissions/day-1
git commit -m "Submit Day 1 Lakebase support app"
git branch -M main
git remote add origin https://github.com/DucDTran/databricks-lakebase-support-app.git
git push -u origin main
```

## Lakebase DDL And Constraints

The DDL is included as:

`lakebase_schema_ddl.sql`

Key constraints from the DDL:

```sql
CREATE TABLE IF NOT EXISTS support_app.tickets (
    ticket_id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    created_by TEXT NOT NULL CHECK (length(trim(created_by)) > 0),
    seed_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS support_app.ticket_messages (
    message_id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES support_app.tickets(ticket_id) ON DELETE CASCADE,
    message_text TEXT NOT NULL CHECK (length(trim(message_text)) > 0),
    author TEXT NOT NULL CHECK (length(trim(author)) > 0),
    seed_key TEXT UNIQUE
);
```

This confirms:

- `support_app.tickets.ticket_id` is the primary key.
- `support_app.ticket_messages.message_id` is the primary key.
- `support_app.ticket_messages.ticket_id` is a foreign key referencing `support_app.tickets(ticket_id)`.
- Deleting a ticket cascades to its messages.
- Status and priority values are constrained by `CHECK` rules.

## Write Evidence

The evidence files in `submissions/day-1/evidence` were captured from the deployed Databricks App API. These API endpoints read from and write to Lakebase through the FastAPI backend, so the after-state JSON files demonstrate persistence in Lakebase.

### Ticket Creation

Evidence ticket:

```json
{
  "ticket_id": 16,
  "title": "Submission evidence ticket",
  "status": "open",
  "priority": "high",
  "category": "submission",
  "message_count": 0,
  "created_by": "dwc.tran@example.com"
}
```

Files:

- `03-create-ticket-response.json`: returned the new `ticket_id`.
- `04-after-create-ticket.json`: immediately read the created ticket back from Lakebase.

### Message Posting

Two messages were posted to ticket `#16`:

```json
[
  {
    "message_id": 30,
    "ticket_id": 16,
    "message_text": "First evidence message posted through the deployed application backend.",
    "author": "dwc.tran@example.com"
  },
  {
    "message_id": 31,
    "ticket_id": 16,
    "message_text": "Second evidence message confirms the related messages table writes are persisted.",
    "author": "support.lead@example.com"
  }
]
```

Files:

- `05-add-message-1-response.json`: returned message `#30`.
- `06-add-message-2-response.json`: returned message `#31`.
- `07-after-add-messages.json`: immediately read both messages back from Lakebase.

### Status Update Persistence

Before status update:

```json
[
  {
    "ticket_id": 16,
    "title": "Submission evidence ticket",
    "status": "open",
    "message_count": 2
  }
]
```

After status update:

```json
[
  {
    "ticket_id": 16,
    "title": "Submission evidence ticket",
    "status": "resolved",
    "message_count": 2
  }
]
```

Files:

- `08-status-before-update.json`: ticket `#16` was `open`.
- `09-status-update-response.json`: the update endpoint returned `resolved`.
- `10-status-after-update.json`: immediately read the same ticket back as `resolved`.

## Final Data Check

Final Lakebase-backed ticket summary:

```json
{
  "ticket_count": 6,
  "statuses": ["in_progress", "open", "resolved"],
  "tickets_below_two_messages": []
}
```

File:

- `11-final-ticket-summary.json`

This addresses the feedback that one ticket was missing a second message. Ticket `#14` was given a second verification message, and the final check confirms there are no tickets with fewer than two messages.

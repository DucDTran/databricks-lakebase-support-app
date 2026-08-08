# Lakebase Support Desk

React + TailwindCSS Databricks App for the Day 1 Lakebase homework. The app is an internal support desk where users can create tickets, add messages, update ticket status, and verify persistence after refresh.

The UI is written with React, Vite, TailwindCSS, and `lucide-react`. The server is a small FastAPI app that serves the built React assets and exposes API routes that read from and write to Lakebase Postgres.

## Features

- View tickets from Lakebase
- Select a ticket and view messages
- Create a new ticket
- Add a message to a ticket
- Update ticket status
- Store operational data in related Lakebase tables
- Preserve changes after refresh
- Bonus: priority and category fields
- Bonus: status filtering
- Bonus: input validation and helpful errors
- Bonus: ticket statistics
- Bonus: delete with confirmation
- Bonus: TailwindCSS app UI inspired by Tailwind Plus application components

## Project Files

- `src/main.tsx`: React application and Tailwind component markup
- `src/styles.css`: Tailwind entrypoint
- `server.py`: FastAPI server, Lakebase connection pool, and API routes
- `schema.sql`: Lakebase schema with `tickets` and `ticket_messages`
- `seed.sql`: idempotent sample data
- `app.yaml`: Databricks Apps runtime config
- `package.json`: React/Vite/Tailwind dependencies and build script
- `package-lock.json`: npm lock file
- `requirements.txt`: Python dependencies
- `docs/databricks-react-app-deploy-research.md`: official-docs deployment notes

## Architecture

Databricks Apps deploys this as a mixed Node/Python app:

1. Databricks sees `package.json`, installs Node dependencies, and runs `npm run build`.
2. Vite writes the production React app to `dist/`.
3. Databricks installs Python dependencies from `requirements.txt`.
4. `app.yaml` starts the app with `python server.py`.
5. FastAPI listens on `0.0.0.0:$DATABRICKS_APP_PORT`, serves `dist/`, and exposes `/api/*`.
6. FastAPI connects to Lakebase through Databricks-managed app resource environment variables.

Lakebase should be added as a Databricks App database resource with resource key `postgres`. Databricks injects standard Postgres variables for the first database resource:

- `PGHOST`
- `PGDATABASE`
- `PGUSER`
- `PGPORT`
- `PGSSLMODE`

`app.yaml` also defines:

```yaml
env:
  - name: ENDPOINT_NAME
    valueFrom: postgres
```

For Lakebase Autoscaling, `valueFrom: postgres` resolves to the endpoint path. The server uses `WorkspaceClient().postgres.generate_database_credential(endpoint=...)` to get temporary OAuth credentials for Postgres connections. Do not hardcode passwords, tokens, PATs, or API keys.

## Local Validation

You can validate frontend and Python syntax locally without Lakebase credentials:

```bash
npm install
npm run build
python3 -m py_compile server.py
npm audit --omit=dev
```

Running the full app locally requires Databricks authentication plus the Lakebase `PG*` variables and `ENDPOINT_NAME`, so the easiest full test is usually in Databricks Apps.

## Step 1: Create Or Open Lakebase

1. Open Databricks Free Edition.
2. Open Lakebase from the app switcher.
3. Create a Lakebase Autoscaling project if you do not already have one.
4. Create or use the default branch and database.
5. Keep the project, branch, database, and endpoint names handy.

Free Edition caveats: one Lakebase project per account, up to three Databricks Apps per account, serverless-only compute, and apps automatically stop after 24 hours from start/update/redeploy.

## Step 2: Create The Databricks App

1. Open Databricks Apps.
2. Click **Create app**.
3. Choose **Custom app** if available.
4. Name the app, for example `lakebase-support-desk`.
5. Add a database resource:
   - Resource type: `Database`
   - Database type/source: your Lakebase Autoscaling database
   - Permission: `Can connect and create`
   - Resource key: `postgres`

The resource key must match `valueFrom: postgres` in `app.yaml`.

## Deploy Option A: Databricks CLI Workspace Sync

Use this path if you want the simplest bootcamp workflow and do not need GitHub.

1. Install or confirm the Databricks CLI:

```bash
databricks --version
```

2. Authenticate to your Free Edition workspace:

```bash
databricks auth login --host https://<your-workspace-host>
```

3. From this project folder, sync the source to a Databricks workspace folder:

```bash
databricks sync . /Workspace/Users/<your-email>/lakebase-support-desk
```

Use `.gitignore` to keep `node_modules/`, `.env`, caches, and local build artifacts out of the upload.

4. Deploy the app from that workspace folder:

```bash
databricks apps deploy lakebase-support-desk \
  --source-code-path /Workspace/Users/<your-email>/lakebase-support-desk
```

5. Open the app from the Databricks Apps page and watch logs if startup fails.

For active editing, use:

```bash
databricks sync --watch . /Workspace/Users/<your-email>/lakebase-support-desk
```

Then redeploy after changes:

```bash
databricks apps deploy lakebase-support-desk \
  --source-code-path /Workspace/Users/<your-email>/lakebase-support-desk
```

## Deploy Option B: GitHub

Use this path if you want cleaner version control or your instructor wants to inspect the repository.

1. Initialize a Git repository:

```bash
git init
git add .
git commit -m "Build Lakebase support desk app"
```

2. Create a GitHub repository, then push:

```bash
git branch -M main
git remote add origin https://github.com/DucDTran/databricks-lakebase-support-app.git
git push -u origin main
```

3. In Databricks Apps, open your app and configure Git:
   - Provider: `GitHub`
   - Repository URL: `https://github.com/DucDTran/databricks-lakebase-support-app`
   - Branch: `main`
   - Source code path: leave empty if this project is the repository root

4. If the repository is private, configure a Git credential for the app service principal. Public repositories do not require this.

5. Deploy from Git in the UI, or use the CLI:

```bash
databricks apps create-update lakebase-support-desk \
  --json '{"update_mask": "git_repository", "git_repository": {"url": "https://github.com/DucDTran/databricks-lakebase-support-app", "provider": "gitHub"}}'

databricks apps deploy lakebase-support-desk \
  --json '{"git_source": {"branch": "main"}}'
```

If the app lives in a subfolder of a larger repository, deploy with `source_code_path`:

```bash
databricks apps deploy lakebase-support-desk \
  --json '{"git_source": {"branch": "main", "source_code_path": "path/to/app"}}'
```

## Step 3: Test The Homework Requirements

Open the deployed app URL and verify:

1. Existing tickets load from Lakebase.
2. There are at least three seeded support tickets.
3. Each seeded ticket has at least two messages.
4. There are at least two statuses. The seed data includes `open`, `in_progress`, and `resolved`.
5. Create a new ticket.
6. Refresh the page and confirm the new ticket remains.
7. Add a message to an existing ticket.
8. Refresh and confirm the message remains.
9. Change a ticket status.
10. Refresh and confirm the status remains changed.
11. Test bonus filtering by status.
12. Test validation by submitting an empty title or message.
13. Test delete only if you are comfortable removing a test ticket.

## Step 4: Capture Lakebase Screenshots

Capture a screenshot of the deployed app and screenshots of Lakebase tables/sample records.

Useful SQL:

```sql
SELECT ticket_id, title, status, priority, category, created_by, created_at
FROM support_app.tickets
ORDER BY ticket_id;

SELECT message_id, ticket_id, message_text, author, created_at
FROM support_app.ticket_messages
ORDER BY ticket_id, message_id;
```

## Step 5: Zip Source For Submission

Run:

```bash
zip -r support_app_source.zip \
  src server.py app.yaml package.json package-lock.json requirements.txt \
  schema.sql seed.sql index.html tailwind.config.js postcss.config.js \
  tsconfig.json vite.config.ts README.md docs \
  -x "node_modules/*" "dist/*" ".env" "__pycache__/*"
```

Submit:

- Databricks App URL
- `support_app_source.zip`
- Screenshot of the deployed app
- Screenshot of Lakebase tables and sample records
- Reflection below

## Reflection Draft

The most difficult part was connecting the deployed app to Lakebase securely while keeping database credentials out of the source code. Lakebase is different from storing this in a traditional analytics table because it behaves like operational Postgres storage: the app can do low-latency inserts, updates, deletes, constraints, and foreign keys, while analytics tables are usually optimized for larger analytical scans and batch transformations. I would add assignee and SLA tracking next so support owners can route tickets, monitor response time, and escalate urgent issues.

## Official Docs Used

- [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)
- [Configure Databricks app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)
- [Manage dependencies for a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies)
- [Databricks Apps environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)
- [Add a Lakebase resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase)
- [Define environment variables in a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/environment-variables)
- [Connect a custom Databricks app to Lakebase](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling)
- [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

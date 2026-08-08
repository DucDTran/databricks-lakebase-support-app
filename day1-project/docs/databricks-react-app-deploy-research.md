# Databricks React/Node App Deployment Research

Research date: 2026-08-05

Scope: official Databricks documentation for deploying a React/Node Databricks App backed by Lakebase Postgres on Databricks Free Edition. This note uses only primary Databricks docs. It does not change the app code in this repository.

## Short Answer

For a React/Node Databricks App backed by Lakebase on Free Edition, the most current Databricks-documented flow is:

1. Put the deployable app root in a directory that contains `package.json`, optional `app.yaml`, dependencies, and the app entry point.
2. Make the Node server listen on `0.0.0.0` and the Databricks-provided port, either through `DATABRICKS_APP_PORT` or the framework variables Databricks sets, such as `PORT` for Express.
3. Attach Lakebase as a Databricks Apps database resource, preferably Lakebase Autoscaling with resource key `postgres`.
4. Reference the resource key from `app.yaml` with `valueFrom` when the app needs the resource-derived endpoint value, and rely on the injected `PG*` variables for the first Lakebase database resource.
5. Deploy from either a synced workspace folder with `databricks apps deploy <app-name> --source-code-path <workspace-path>` or from Git with `databricks apps deploy <app-name> --json '{"git_source": ...}'`.

Free Edition supports the learning/prototyping shape of this workflow, but it is quota-limited: serverless only, up to 3 apps per account, one Lakebase project, apps stop after 24 hours from start/update/redeploy, and compute can be shut down when quotas are exceeded. Sources: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy), [Configure Databricks app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime), [Add a Lakebase resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase), [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations).

## React/Node App Runtime Requirements

Databricks Apps supports Python apps, Node.js apps, and mixed Python/Node apps. During deployment, Databricks checks for a root `package.json` to determine whether Node.js build steps are needed. If `package.json` is present, deployment installs Node dependencies, installs Python dependencies if Python dependency files are present, runs the `build` script when `package.json` defines one, then runs the command from `app.yaml`; for `npm` apps without an `app.yaml` command, Databricks runs `npm run start`. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

For Node dependencies, Databricks requires `package.json` in the root of the app. If `pnpm-lock.yaml` exists, Databricks uses `pnpm`; otherwise it uses `npm`. If both `pnpm-lock.yaml` and `package-lock.json` exist, `pnpm` takes precedence. Databricks' React/Vite example puts the React/Vite packages needed for the build step under `dependencies`; Databricks warns that packages needed during build should not be only in `devDependencies` when `NODE_ENV=production`, because deployment skips `devDependencies` in that case. Source: [Manage dependencies for a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies).

The Databricks Apps runtime currently documents Node.js version 22.16. It also states that no Node.js libraries are pre-installed, so all Node dependencies must be listed in `package.json`. Source: [Databricks Apps environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env).

Platform requirements matter for the Node server: Databricks says apps must listen on `0.0.0.0` and use the port specified by `DATABRICKS_APP_PORT`. The runtime also sets framework variables; for Express, Databricks sets `PORT`. Sources: [Best practices for Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/best-practices), [Databricks Apps environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env).

## `app.yaml` Command Requirements For React/Node

`app.yaml` is optional, can also use the `.yml` extension, and must be located at the root of the project directory. It defines how the app runs when the default behavior is not enough. Source: [Configure Databricks app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime).

The documented top-level settings are:

- `command`: a sequence for a custom command. For Node apps using `npm`, the fallback is `npm run start` when no command is supplied.
- `env`: a list of additional environment variables. Each item has `name` plus either `value` or `valueFrom`.

Databricks does not run the `command` in a shell. As a result, shell environment variables defined outside `app.yaml` are not available to the command. The documented exception is `DATABRICKS_APP_PORT`, which Databricks substitutes with the actual port number at runtime. Source: [Configure Databricks app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime).

For a typical `npm` React/Node app, `app.yaml` can be limited to environment configuration when `npm run start` starts the production server correctly:

```yaml
env:
  - name: ENDPOINT_NAME
    valueFrom: postgres
```

Use an explicit command when the app needs a non-default start command, needs to pass the Databricks port as a CLI argument, or uses `pnpm`. Databricks documents that `pnpm` apps must specify the start command in `app.yaml`; `pnpm` apps do not fall back to a default `start` script. For `pnpm` workspace commands that recurse, Databricks says to call `corepack pnpm` instead of bare `pnpm` so nested commands resolve correctly. Source: [Manage dependencies for a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies).

Example shape for an explicit Node command:

```yaml
command:
  - npm
  - run
  - start
  - --
  - --host
  - 0.0.0.0
  - --port
  - "$DATABRICKS_APP_PORT"
env:
  - name: ENDPOINT_NAME
    valueFrom: postgres
```

The exact flags after `--` must match the Node server being used. An Express app usually reads `process.env.PORT` instead of requiring a `--port` CLI flag; a Vite preview or custom server may need its own host/port flags.

For mixed Python/Node apps, Databricks notes that if `package.json` is present and no command is specified, it still executes `npm run start`, even when Python code is present. To run both a Node and Python process, Databricks recommends defining a custom `start` script using a process runner such as `concurrently`. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

## CLI Workspace Sync And Deploy Flow

Databricks documents workspace-folder deployment as the standard deployment method. The CLI flow is:

1. Open a terminal in the local directory that contains the app files.
2. Upload files to a workspace folder:

```bash
databricks sync --watch . /Workspace/Users/my-email@org.com/my-app
```

3. Verify the files in the Databricks workspace.
4. Deploy from that workspace source path:

```bash
databricks apps deploy my-app-name \
  --source-code-path /Workspace/Users/my-email@org.com/my-app
```

The `--watch` flag keeps syncing local edits. Databricks recommends using `.gitignore` to exclude files such as `node_modules/`, `.env`, caches, `.DS_Store`, large data files, and build artifacts. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

The Databricks CLI reference describes `--source-code-path` as the workspace file system path of the source code used to create the app deployment. The same CLI reference also documents deployment modes such as `AUTO_SYNC` and `SNAPSHOT`, with examples using `--source-code-path`. Source: [`apps` command group](https://docs.databricks.com/aws/en/dev-tools/cli/reference/apps-commands).

For a Lakebase-backed app, Databricks' custom Lakebase tutorial shows the same two-step command sequence:

```bash
databricks sync . /Workspace/Users/<your-email>/my-lakebase-app
databricks apps deploy <app-name> --source-code-path /Workspace/Users/<your-email>/my-lakebase-app
```

Databricks explains that `--source-code-path` tells deployment to use the uploaded files rather than the app's default location. Source: [Connect a custom Databricks app to Lakebase](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling).

After deployment, Databricks starts the app according to `app.yaml` or the documented defaults, and the app overview page provides status, logs, deployment history, and environment information. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

## Git-Based Deployment Flow

Databricks supports deploying Apps directly from Git repositories. The Git repository must contain the app files, including `app.yaml`, dependencies, and the entry point. Databricks lists major providers including GitHub, GitLab, Bitbucket, Azure DevOps, and AWS CodeCommit in the CLI flow. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

UI flow:

1. Push the app files to Git.
2. Create or edit a Databricks App.
3. Configure the Git repository URL and provider at the app level.
4. For private repositories, configure a Git credential for the app service principal.
5. Deploy from Git by selecting a branch, tag, or commit SHA.
6. Optionally set Source code path when the app root is a subdirectory; Databricks treats that directory as the top-level app directory and does not let the app access files outside it.

CLI flow for a new app:

```bash
databricks apps create my-app \
  --json '{"git_repository": {"url": "<repo-url>", "provider": "gitHub"}}'
```

CLI flow for an existing app:

```bash
databricks apps create-update my-app \
  --json '{"update_mask": "git_repository", "git_repository": {"url": "<repo-url>", "provider": "gitHub"}}'
```

Deploy from a branch:

```bash
databricks apps deploy my-app \
  --json '{"git_source": {"branch": "main"}}'
```

Deploy from a tag or commit:

```bash
databricks apps deploy my-app \
  --json '{"git_source": {"tag": "v1.0.0"}}'

databricks apps deploy my-app \
  --json '{"git_source": {"commit": "abc123def456"}}'
```

Deploy from a subdirectory in the repository:

```bash
databricks apps deploy my-app \
  --json '{"git_source": {"branch": "main", "source_code_path": "apps/my-app"}}'
```

For branch or tag references, Databricks deploys the most recent commit from that branch or tag. For a commit SHA, it deploys that exact commit. If the app service principal's Git credential is invalid or expired, deployment fails. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

Automatic Git deployments are documented as Beta. During Beta, Databricks supports GitHub and Azure DevOps for automatic deployments. The Git reference must be a branch; tags are not compatible with automatic deployments. For GitHub automatic deployment, Databricks requires the Databricks GitHub app to be installed, the repository to be private, and the app service principal to have a Git credential with access to the repository. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

Workspace admins can enforce Git-only deployments. When enabled, users must configure Git before creating an app, can only deploy from Git, cannot use app templates, and existing apps cannot be redeployed or started unless they have a Git repository. Source: [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy).

## Lakebase Resource, Environment Variables, And `valueFrom`

Databricks defines app resources as Databricks platform features connected to an app, such as Lakebase databases, SQL warehouses, secrets, jobs, model serving endpoints, Unity Catalog assets, and other apps. Databricks recommends app resources because they manage credentials, permissions, paths, endpoints, and connection details without hardcoding them in app code. Source: [Add resources to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources).

Lakebase is a fully managed Postgres database integrated into Databricks. Databricks lists app backends as a Lakebase use case, and the Apps resource docs describe Lakebase database resources as PostgreSQL storage/querying resources for Databricks Apps. Sources: [Lakebase Postgres](https://docs.databricks.com/aws/en/oltp/projects/), [Add resources to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources).

To add Lakebase as an app resource:

1. In the App resources section when creating or editing an app, choose Add resource > Database.
2. For Lakebase Autoscaling, select the project, branch, and database.
3. Select the currently documented permission, Can connect and create.
4. Optionally set a custom resource key. The default key is `postgres` for Lakebase Autoscaling and `database` for Lakebase Provisioned.

The user adding a Lakebase Autoscaling resource must have `CAN MANAGE` on the Lakebase project. Source: [Add a Lakebase resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase).

When a database resource is added, Databricks creates or reuses a PostgreSQL role in the selected database. The role name matches the app service principal's client ID. Databricks grants that service principal `CONNECT` and `CREATE` privileges on the selected database. Source: [Add a Lakebase resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase).

For the first database resource attached to an app, Databricks sets these standard Postgres environment variables:

| Variable | Meaning |
| --- | --- |
| `PGAPPNAME` | App name |
| `PGDATABASE` | Database name |
| `PGHOST` | PostgreSQL server host |
| `PGPORT` | PostgreSQL server port |
| `PGSSLMODE` | SSL mode |
| `PGUSER` | Service principal client ID and Postgres role name |

If multiple PostgreSQL databases are attached, the default `PG*` variables reflect only the first database resource. Source: [Add a Lakebase resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase).

`valueFrom` connects an `app.yaml` environment variable to the resource key configured on the app. Databricks' current `valueFrom` reference says:

| Resource type | `valueFrom` resolved value |
| --- | --- |
| Lakebase Autoscaling database | Endpoint path, for example `projects/my-project/branches/main/endpoints/ep123` |
| Lakebase Provisioned database | Host, for example `postgres-host.example.com` |

Source: [Define environment variables in a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/environment-variables).

Example `app.yaml` for a React/Node app using a Lakebase Autoscaling resource key named `postgres`:

```yaml
env:
  - name: ENDPOINT_NAME
    valueFrom: postgres
```

In app code, a Node process can read that value with `process.env.ENDPOINT_NAME`. Databricks' environment variable docs show JavaScript access through `process.env`, and the Lakebase custom app tutorial uses the endpoint value with `generate_database_credential()` to mint fresh database credentials for Lakebase Autoscaling. Sources: [Define environment variables in a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/environment-variables), [Connect a custom Databricks app to Lakebase](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling).

Lakebase Autoscaling OAuth credentials expire after one hour. Databricks' custom Lakebase tutorial says long-running apps should generate fresh credentials before use, commonly by using a connection pool that creates new connections with fresh OAuth tokens. Source: [Connect a custom Databricks app to Lakebase](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling).

Databricks notes that Lakebase database state persists across app redeploys and stops. If an existing app uses a Lakebase Provisioned `database` resource and is upgraded to Autoscaling, Databricks says not to change the resource type from `database` to `postgres`; those resource types create separate Postgres roles, and changing it can break access to existing data. Source: [Add a Lakebase resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase).

## Free Edition Caveats

Databricks Free Edition is a no-cost offering for learning, prototyping, and experimentation, but Databricks explicitly says it does not include guaranteed reliability, support, or service-level agreements. It is subject to Databricks fair usage policy. Sources: [Sign up for Databricks Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition), [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations).

Relevant Free Edition limits and caveats for a React/Node Lakebase-backed app:

- Serverless-only: Free Edition users only have serverless compute resources; custom compute configurations are not supported.
- Restricted outbound internet: outbound internet access is restricted to a limited set of trusted domains. This can matter when deploying Node apps that need npm packages or external APIs.
- Apps quota: up to 3 Databricks Apps per account.
- App lifetime: apps run for up to 24 hours after being started, updated, or redeployed, then Databricks automatically stops them. They can be restarted.
- Lakebase quota: one Lakebase project per account, with scale-to-zero compute.
- Quota shutdowns: if quotas are exceeded, workspace compute resources can be shut down for the rest of the day and, in extreme cases, the rest of the month. Databricks says data and settings are not deleted.
- LinkedIn verification: some Free Edition feature limits can increase after LinkedIn verification; Databricks specifically lists limited serverless GPU compute and outbound internet access.
- Unsupported/admin caveats: no R or Scala, no custom workspace storage locations, no account console or account-level APIs, no compliance enforcement, no security customization, no private networking configurations, no SSO or SCIM support, and non-commercial use only.

Source: [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations).

## Practical Checklist

Before deploying a React/Node Lakebase-backed Databricks App on Free Edition:

1. Confirm the deploy root contains `package.json`; keep `app.yaml` in that same root if needed.
2. Put all Node build-time packages under `dependencies` if `NODE_ENV=production` may be set.
3. Make `npm run build` work if a `build` script is present; Databricks runs it during deployment.
4. Make `npm run start` start the production app, or define `command` explicitly in `app.yaml`.
5. Ensure the server listens on `0.0.0.0` and the Databricks-provided port.
6. Add Lakebase as an app Database resource with key `postgres` for Autoscaling unless you intentionally choose a custom key.
7. Add `env: [{ name: ENDPOINT_NAME, valueFrom: postgres }]` or equivalent YAML when the app needs the Lakebase endpoint path.
8. Use the injected `PG*` variables for first-resource connection parameters.
9. Use Databricks OAuth credential rotation for Lakebase Autoscaling connections instead of storing passwords or PATs.
10. Deploy from either a workspace folder using `--source-code-path` or a configured Git repository using `git_source`.
11. Expect Free Edition apps to stop after 24 hours and Lakebase to scale to zero when idle.

## Source List

- [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)
- [Configure Databricks app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)
- [Manage dependencies for a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies)
- [Databricks Apps environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)
- [Best practices for Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/best-practices)
- [Add resources to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)
- [Define environment variables in a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/environment-variables)
- [Add a Lakebase resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase)
- [Connect a custom Databricks app to Lakebase](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling)
- [Lakebase Postgres](https://docs.databricks.com/aws/en/oltp/projects/)
- [Sign up for Databricks Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition)
- [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

# Weather Intelligence: Unstructured Data → Lakebase Vector Search → REST API

This project uses the National Weather Service (NWS) API as its unstructured
weather source. NWS is free, does not require an API key, and provides useful
free-text fields such as alert descriptions, alert instructions, headlines,
and `detailedForecast` narrative text. The NWS API requires an identifying
`User-Agent`, which the client supplies and allows callers to override with
`NWS_USER_AGENT` in a deployment environment if desired.

## What is included

- `weather_client.py` resolves city/state or coordinate inputs, calls NWS
  `/points`, fetches active point alerts and 12-hour forecast periods, and
  normalizes them into stable `WeatherDocument` records.
- `lakebase.py` contains the psycopg2 Lakebase connection helper, idempotent
  DDL, document upsert, embedding batch insert, and pgvector cosine search.
- `ingest_weather_embeddings.py` reads documents without embeddings, chunks
  the narrative, embeds chunks, and writes vectors with psycopg2.
- `embedding.py` lazily loads the shared
  `sentence-transformers/all-MiniLM-L6-v2` model once per process.
- `app.py` exposes `POST /weather/sync` and `POST /weather/search`.
- `schema.sql` is the equivalent standalone migration for running in a SQL
  editor.

## Schema decisions

`weather_documents` is the provenance-preserving document table:

- `id TEXT PRIMARY KEY` is a stable NWS alert URL/id or a SHA-256 key derived
  from location, forecast period, and valid time.
- `location`, `source_type`, `headline`, and `narrative_text` make the record
  easy to inspect and filter.
- `issued_at` and `effective_at` preserve time semantics when NWS provides
  them.
- `payload JSONB` keeps the original alert/forecast JSON for provenance and
  future parsing.
- `synced_at`, `created_at`, and `updated_at` support repeatable ingestion.

`weather_embeddings` stores one row per chunk. It uses the same
`all-MiniLM-L6-v2` model for both ingestion and query embedding, so the column
is `vector(384)`. Chunks use an 800-character sliding window with 100
characters of overlap. NWS text is usually short, but this prevents longer
alert descriptions plus instructions from becoming one oversized retrieval
unit. The unique `(document_id, chunk_index)` constraint makes re-running the
embedding job safe, and the HNSW `vector_cosine_ops` index supports cosine
distance search.

## Run the pipeline

### 1. Configure Lakebase

In Databricks Apps, attach the Lakebase database as a resource with key
`postgres`. Databricks supplies `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPORT`, and
`PGSSLMODE`; `app.yaml` maps the resource endpoint to `ENDPOINT_NAME` so the
app can request a short-lived database credential through the Databricks SDK.

For local development, set `PGHOST`, `PGDATABASE`, `PGUSER`, and
`PGPASSWORD` (or set `DATABASE_URL`). The connection helper uses SSL by
default. Apply `schema.sql` manually, or let either API endpoint or the
embedding script apply its idempotent migration automatically.

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the REST API

```bash
python app.py
```

The app listens on port 8000 locally, or on `DATABRICKS_APP_PORT` when run as
a Databricks App.

### 3. Harvest weather documents

City/state input is supported through the public Nominatim/OpenStreetMap
geocoder; NWS remains the weather data source. The geocoder is used only to
turn a human-readable place into coordinates and is not ingested as weather
content. Coordinates can also be supplied as strings or
objects if you want to avoid geocoding:

```bash
curl -X POST http://127.0.0.1:8000/weather/sync \
  -H 'Content-Type: application/json' \
  -d '{"locations":["Chicago, IL","Austin, TX"],"limit":50}'
```

Example coordinate forms are `"39.7456,-97.0892"`, `[39.7456, -97.0892]`,
and `{"label":"Denver, CO","lat":39.7392,"lon":-104.9903}`.

The endpoint upserts by stable document id, so repeated syncs do not create
duplicate documents. A successful response includes `count` and
`documents_synced`.

### 4. Embed the harvested documents

Run the plain Python job from this directory:

```bash
python ingest_weather_embeddings.py --limit 200
```

The job reads only documents that have no chunks yet, batches model inference,
and uses psycopg2 `execute_values` with an explicit `%s::vector` cast. It does
not use Spark JDBC. Use `--dry-run` to perform embedding work without writing
rows. If you process a different embedding model, it must still produce 384
dimensions unless you also migrate the vector column and update the API.

### 5. Search semantically

```bash
curl -X POST http://127.0.0.1:8000/weather/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"flash flood risk this weekend","top_k":5}'
```

The search endpoint clamps `top_k` to 1–20, embeds the query with the same
model used by the batch job, and executes pgvector cosine distance:

```sql
1 - (e.embedding <=> %s::vector)
```

If the table has not been embedded yet, the endpoint returns a successful
response with an empty `results` array.

## Known limitations and next improvements

- NWS coverage is U.S.-focused and active alerts are point-filtered; a
  location near a boundary may not include every nearby county or zone alert.
- City/state geocoding uses the public Nominatim endpoint and is intentionally
  lightweight. Production code should cache coordinates and add retry/backoff
  handling for geocoder and NWS rate limits.
- Forecast rows use each period's `startTime` as `effective_at`; NWS forecast
  issuance metadata is not duplicated into a separate field.
- Retrieval is chunk-level, so the same document can appear more than once if
  several chunks are highly relevant. A future version could group results by
  document and add a source-type/location filter.
- The optional stretch goal of an LLM-generated summary is left out so this
  submission remains a focused, deterministic vector retrieval pipeline.

## Official source

The implementation follows the NWS API documentation for `/points`, forecast
URLs, active alerts, ISO-8601 timestamps, rate limits, and the required
identifying `User-Agent`: <https://www.weather.gov/documentation/services-web-api>.

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import psycopg
import uvicorn
from databricks.sdk import WorkspaceClient
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field


STATUSES = ("open", "in_progress", "resolved", "closed")
PRIORITIES = ("low", "medium", "high", "urgent")
DIST_DIR = Path(__file__).parent / "dist"


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    created_by: str = Field(min_length=1, max_length=120)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    category: str = Field(default="general", min_length=1, max_length=80)


class MessageCreate(BaseModel):
    message_text: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=120)


class StatusUpdate(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"]


class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        workspace = WorkspaceClient()
        credential = workspace.postgres.generate_database_credential(
            endpoint=os.environ["ENDPOINT_NAME"]
        )
        kwargs["password"] = credential.token
        return super().connect(conninfo, **kwargs)


def missing_config() -> list[str]:
    required = ["PGHOST", "PGDATABASE", "PGUSER", "ENDPOINT_NAME"]
    return [name for name in required if not os.getenv(name)]


def create_pool() -> ConnectionPool:
    missing = missing_config()
    if missing:
        raise RuntimeError(
            "Missing Lakebase connection settings: " + ", ".join(missing)
        )

    conninfo = (
        f"dbname={os.environ['PGDATABASE']} "
        f"user={os.environ['PGUSER']} "
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"sslmode={os.environ.get('PGSSLMODE', 'require')}"
    )
    return ConnectionPool(
        conninfo=conninfo,
        connection_class=OAuthConnection,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
        open=True,
    )


pool: ConnectionPool | None = None


def execute_sql_file(path: str) -> None:
    assert pool is not None
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(Path(path).read_text(encoding="utf-8"))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = create_pool()
    execute_sql_file("schema.sql")
    execute_sql_file("seed.sql")
    yield
    if pool is not None:
        pool.close()


app = FastAPI(title="Lakebase Support Desk", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_pool() -> ConnectionPool:
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not ready")
    return pool


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/tickets")
def list_tickets(status: str | None = None):
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status filter")

    where_clause = ""
    params = ()
    if status:
        where_clause = "WHERE t.status = %s"
        params = (status,)

    query = """
        SELECT
            t.ticket_id,
            t.title,
            t.description,
            t.status,
            t.priority,
            t.category,
            t.created_by,
            t.created_at,
            t.updated_at,
            count(m.message_id)::int AS message_count
        FROM support_app.tickets t
        LEFT JOIN support_app.ticket_messages m ON m.ticket_id = t.ticket_id
        {where_clause}
        GROUP BY t.ticket_id
        ORDER BY
            CASE t.priority
                WHEN 'urgent' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            t.created_at DESC
    """.format(where_clause=where_clause)
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


@app.post("/api/tickets", status_code=201)
def create_ticket(ticket: TicketCreate):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO support_app.tickets
                    (title, description, created_by, priority, category)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING ticket_id
                """,
                (
                    ticket.title.strip(),
                    ticket.description.strip(),
                    ticket.created_by.strip(),
                    ticket.priority,
                    ticket.category.strip().lower(),
                ),
            )
            created = cur.fetchone()
        conn.commit()
    return created


@app.get("/api/tickets/{ticket_id}/messages")
def list_messages(ticket_id: int):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticket_id FROM support_app.tickets WHERE ticket_id = %s",
                (ticket_id,),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Ticket not found")
            cur.execute(
                """
                SELECT message_id, ticket_id, message_text, author, created_at
                FROM support_app.ticket_messages
                WHERE ticket_id = %s
                ORDER BY created_at ASC, message_id ASC
                """,
                (ticket_id,),
            )
            return cur.fetchall()


@app.post("/api/tickets/{ticket_id}/messages", status_code=201)
def add_message(ticket_id: int, message: MessageCreate):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticket_id FROM support_app.tickets WHERE ticket_id = %s",
                (ticket_id,),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Ticket not found")
            cur.execute(
                """
                INSERT INTO support_app.ticket_messages (ticket_id, message_text, author)
                VALUES (%s, %s, %s)
                RETURNING message_id
                """,
                (ticket_id, message.message_text.strip(), message.author.strip()),
            )
            created = cur.fetchone()
            cur.execute(
                "UPDATE support_app.tickets SET updated_at = now() WHERE ticket_id = %s",
                (ticket_id,),
            )
        conn.commit()
    return created


@app.patch("/api/tickets/{ticket_id}/status")
def update_status(ticket_id: int, update: StatusUpdate):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE support_app.tickets
                SET status = %s, updated_at = now()
                WHERE ticket_id = %s
                RETURNING ticket_id, status
                """,
                (update.status, ticket_id),
            )
            updated = cur.fetchone()
            if updated is None:
                raise HTTPException(status_code=404, detail="Ticket not found")
        conn.commit()
    return updated


@app.delete("/api/tickets/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM support_app.tickets WHERE ticket_id = %s",
                (ticket_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Ticket not found")
        conn.commit()


if DIST_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=DIST_DIR / "assets"),
        name="assets",
    )


@app.get("/{full_path:path}", response_class=HTMLResponse)
def serve_react_app(full_path: str):
    index = DIST_DIR / "index.html"
    if not index.exists():
        return HTMLResponse(
            """
            <main style="font-family: system-ui; margin: 3rem; max-width: 48rem">
              <h1>React build not found</h1>
              <p>Run <code>npm install</code> and <code>npm run build</code>,
              then restart the app.</p>
            </main>
            """,
            status_code=503,
        )
    return HTMLResponse(index.read_text(encoding="utf-8"))


if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

# lc-demo — practical LangChain v1 tutorial

[![tests](https://github.com/Eduardo-Lucas/lc-demo/actions/workflows/tests.yml/badge.svg)](https://github.com/Eduardo-Lucas/lc-demo/actions/workflows/tests.yml)

Models, structured output, tools, RAG, memory and MCP in one runnable project.

## Structure

```
lc-demo/
├── pyproject.toml          # uv project, deps + `lc-demo` CLI entry point
├── .env.example            # copy to .env and fill in keys
├── docker-compose.yml      # Postgres + pgvector (port 5433)
├── data/
│   └── manual_ecf.txt      # RAG source (sample text)
├── mcp_servers/
│   └── fiscal_server.py    # FastMCP server, launched over stdio
├── src/lc_demo/
│   ├── config.py           # env settings and paths
│   ├── models.py           # steps 2–3: init_chat_model + structured output
│   ├── tools.py            # step 4: local @tool functions
│   ├── rag.py              # step 5: pgvector store + search_manual tool + `lc-demo-ingest`
│   ├── mcp_client.py       # step 7: MCP tools as LangChain tools
│   ├── agent.py            # steps 4/6/7: create_agent factory
│   ├── auth.py             # Postgres users table (scrypt hashes) + `lc-demo-adduser`
│   ├── db.py               # Postgres: LangGraph checkpointer + conversations table
│   ├── web.py              # Streamlit chat UI with login and per-user threads
│   └── main.py             # CLI: one command per step + chat REPL
└── tests/
    ├── test_tools.py       # unit tests (no API keys needed)
    ├── test_auth.py
    ├── test_db.py          # these two are skipped unless Postgres is running
    └── test_rag.py         # pgvector with fake embeddings, no API key needed
```

## Run

```bash
uv sync
cp .env.example .env        # add your keys
docker-compose up -d        # Postgres + pgvector, for rag/chat and the web UI
uv run pytest               # no API keys needed; DB tests skip if Postgres is down
uv run ruff check .         # lint (also runs in CI)
uv run lc-demo basic        # basic | structured | agent | rag | memory | mcp | chat | all
uv run lc-demo chat         # every tool + conversation memory
```

`rag` (and `chat`) need Postgres and `OPENAI_API_KEY` for embeddings. The manual is chunked,
embedded and stored in the `manual_chunks` table on first use; after editing `data/` or changing
`LC_EMBEDDING_MODEL`, rebuild it with `uv run lc-demo-ingest`. Everything else only needs the
model provider's key. Change `LC_MODEL` in `.env` to switch providers.

## Web UI

```bash
docker-compose up -d                       # Postgres on localhost:5433
uv run lc-demo-adduser edu                 # prompts for a password; rerun to reset it
uv run streamlit run src/lc_demo/web.py    # http://localhost:8501
```

Users (scrypt-hashed passwords in a `users` table), conversations and agent memory
(`AsyncPostgresSaver` plus a `conversations` table) are all stored in Postgres, so they
survive restarts. Each user only sees their own chats, which
are titled after their first message and can be deleted from the sidebar. Replies stream token
by token, and tool calls show inline. Set `DATABASE_URL` to use another Postgres.
The CLI demos keep conversation memory in `InMemorySaver`.

## Deploy (Streamlit Community Cloud + Neon)

1. Create a Neon project in a US region and copy its **direct** connection string
   (host without `-pooler`). pgvector is available there; the app enables it.
2. `cp cloud-secrets.example.toml cloud-secrets.toml` and fill it in (it's gitignored).
3. Set up the Neon database from your machine (creates tables, indexes the manual, adds a user):
   ```bash
   export DATABASE_URL='<neon url>'
   uv run lc-demo-ingest
   uv run lc-demo-adduser <username>
   ```
4. On share.streamlit.io: **Create app** → this repo, branch `main`, main file
   `src/lc_demo/web.py`. Under **Advanced settings**, pick Python 3.13 and paste
   `cloud-secrets.toml` into **Secrets**.

Community Cloud installs from `uv.lock`. Top-level secrets become environment variables,
so the code reads them exactly like `.env`.

## Design notes

- Each concept lives in its own module; `agent.py` is the only place that combines them.
- Tools are plain functions, so they can be unit-tested without an LLM.
- Everything runs async because MCP tools are async-only.
- Production swaps: stdio MCP → `streamable_http`, password login → Streamlit's built-in OIDC (`st.login`) or your identity provider.
- Streamlit reruns are sync and MCP tools are async-only, so `web.py` keeps one event loop
  in a background thread and bridges the agent's async stream into `st.write_stream`.

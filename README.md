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
│   └── manual/             # RAG source: every UTF-8 .txt here is indexed (ECF manual, leiaute 12)
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
uv sync --group dev         # dev group (pytest, ruff) is opt-in, so deploys skip it
cp .env.example .env        # add your keys
docker-compose up -d        # Postgres + pgvector, for rag/chat and the web UI
uv run pytest               # no API keys needed; DB tests skip if Postgres is down
uv run ruff check .         # lint (also runs in CI)
uv run lc-demo basic        # basic | structured | agent | rag | memory | mcp | chat | all
uv run lc-demo chat         # every tool + conversation memory
```

`rag` (and `chat`) need Postgres and `OPENAI_API_KEY` for embeddings. Every `.txt` in
`data/manual/` is chunked, embedded and stored in the `manual_chunks` table on first use, and
search results name the file each passage came from. Everything else only needs the model
provider's key.

To update the manual, add or replace files in `data/manual/` (UTF-8; `lc-demo-ingest` refuses
other encodings and prints the `iconv` command to convert), then rebuild with
`uv run lc-demo-ingest` (prefix `DATABASE_URL=...` for Neon) and commit the files. The rebuild
fills a side table and swaps it in within one transaction, so searches keep working throughout.
Rebuild and reboot after changing `LC_EMBEDDING_MODEL`. Change `LC_MODEL` in `.env` to switch providers.

## Web UI

```bash
docker-compose up -d                       # Postgres on localhost:5433
uv run lc-demo-adduser you@example.com     # optional: people can also sign up in the app
uv run streamlit run src/lc_demo/web.py    # http://localhost:8501
```

Users (self-service sign-up with email; scrypt-hashed passwords in a `users` table), conversations and agent memory
(`AsyncPostgresSaver` plus a `conversations` table) are all stored in Postgres, so they
survive restarts. Each user only sees their own chats, which
are titled after their first message and can be deleted from the sidebar. Replies stream token
by token, and tool calls show inline. Set `DATABASE_URL` to use another Postgres.

Each user gets `LC_DAILY_MESSAGE_LIMIT` messages a day (default 20) and the whole app stops at
`LC_MONTHLY_BUDGET_USD` per month (default 20), metered from the token counts each reply reports
(`usage.py`, `usage_log` table). Set `LC_PRICE_*_PER_MTOK` if you change `LC_MODEL`. `LC_EFFORT`
(default `low`) sets how much current Claude models think before answering; models that don't support
it ignore it. Also set a
spend limit in the Anthropic and OpenAI consoles as a hard ceiling.

"Esqueceu a senha?" emails a single-use reset link (valid 30 minutes, only its hash is stored)
through any SMTP provider (`mailer.py`). It appears once `SMTP_HOST`, `SMTP_USERNAME`,
`SMTP_PASSWORD`, `SMTP_FROM` and `APP_URL` are set; see `cloud-secrets.example.toml`.

Sign-up is open to anyone who can reach the app, and every chat uses your API keys.
Sign-up never changes an existing account; to reset a password, rerun `lc-demo-adduser`.
The CLI demos keep conversation memory in `InMemorySaver`.

## Deploy (Streamlit Community Cloud + Neon)

1. Create a Neon project in a US region and copy its **direct** connection string
   (host without `-pooler`). pgvector is available there; the app enables it.
2. `cp cloud-secrets.example.toml cloud-secrets.toml` and fill it in (it's gitignored).
3. Set up the Neon database from your machine (creates tables, indexes the manual, adds a user):
   ```bash
   export DATABASE_URL='<neon url>'
   uv run lc-demo-ingest
   uv run lc-demo-adduser <email>
   ```
4. On share.streamlit.io: **Create app** → this repo, branch `main`, main file
   `src/lc_demo/web.py`. Under **Advanced settings**, pick Python 3.13 and paste
   `cloud-secrets.toml` into **Secrets**.

Community Cloud installs from `uv.lock` (without the dev group). Top-level secrets become environment variables,
so the code reads them exactly like `.env`.

## Design notes

- Each concept lives in its own module; `agent.py` is the only place that combines them.
- Tools are plain functions, so they can be unit-tested without an LLM.
- Everything runs async because MCP tools are async-only.
- Production swaps: stdio MCP → `streamable_http`, password login → Streamlit's built-in OIDC (`st.login`) or your identity provider.
- Streamlit reruns are sync and MCP tools are async-only, so `web.py` keeps one event loop
  in a background thread and bridges the agent's async stream into `st.write_stream`.

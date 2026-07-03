# PostgreSQL + pgvector on ICRN (no docker, no sudo)

Status: Manual — awaiting user execution

Follow this after vLLM is running on the ICRN H200 (Task C4). At the end, the FastAPI backend's tools query a real PostgreSQL with real UIUC course data instead of failing with `psycopg.OperationalError: Connection refused`.

## What this guide gets you

Four processes running side-by-side in the same ICRN JupyterLab session:

- **Terminal 1**: `vllm serve` on port `8000` (already running from Task C4)
- **Terminal 2**: `postgres` (this guide) on port `5432`
- **Terminal 3**: `uvicorn` FastAPI backend on port `8001`, `LLM_BACKEND=vllm_remote` **and** `DATABASE_URL` pointing at localhost Postgres
- **Terminal 4**: your `curl` shell for testing

## Prereqs

- vLLM is running (Task C4 done).
- The `.venv` you built for the backend is still there at `~/IlliniGuide/backend/.venv`.
- `conda` is available in the JupyterLab session. Verify:

```bash
which conda
conda --version
```

If `conda` is missing, stop and ping me — we have alternatives (source-build) but conda is far the smoothest path on ICRN.

---

## Step 1 — Create a dedicated conda env for Postgres

We do **not** install Postgres into the same env as PyTorch/vLLM. Two reasons:

1. Postgres is a **server process**, not a Python library; it lives outside our Python venv anyway.
2. Isolating it means we can `conda remove` it later without touching the ML env.

Open **Terminal 2** in JupyterLab (Terminal 1 is your vLLM):

```bash
conda create -y -n pg -c conda-forge postgresql pgvector
```

**You should see** conda downloading `postgresql-16.x` and `pgvector-x.x.x` and finishing with:

```
done
#
# To activate this environment, use
#     $ conda activate pg
```

This takes ~2 minutes. `pgvector` is the extension our `course_chunks.embedding` column uses (see `backend/app/db/models.py`) — the SQLAlchemy import `from pgvector.sqlalchemy import Vector` will fail on `CREATE TABLE` without it.

Activate the env:

```bash
conda activate pg
```

Verify:

```bash
which postgres
postgres --version
```

**You should see** something like `/home/jackj6/.conda/envs/pg/bin/postgres` and `postgres (PostgreSQL) 16.x`.

---

## Step 2 — Initialize a Postgres data directory

Postgres stores everything (data, config, WAL logs) in a **data directory**. We put ours under our home directory, so no root/system config is touched.

```bash
export PGDATA=$HOME/pgdata
initdb -D $PGDATA --username=illiniguideserve --pwfile=<(echo "illiniguideserve")
```

**What each flag means:**

| Flag | Meaning |
|---|---|
| `-D $PGDATA` | data directory location |
| `--username=illiniguideserve` | superuser name for this cluster (matches our `.env.example`) |
| `--pwfile=<(echo "illiniguideserve")` | password for that superuser, piped in via a bash process substitution so it never lands in shell history |

**You should see** several lines ending with:

```
Success. You can now start the database server using:
    pg_ctl -D /home/jackj6/pgdata -l logfile start
```

---

## Step 3 — Start Postgres

```bash
pg_ctl -D $PGDATA -l $PGDATA/server.log -o "-p 5432" start
```

**Flag breakdown:**

- `-l $PGDATA/server.log` — where Postgres writes its own logs (peek here if anything is off)
- `-o "-p 5432"` — port to listen on (5432 is Postgres's default; our `DATABASE_URL` expects it)

**You should see**:

```
waiting for server to start.... done
server started
```

Sanity check that it's alive and accepting connections:

```bash
psql -h localhost -p 5432 -U illiniguideserve -d postgres -c "SELECT version();"
```

Password prompt: type `illiniguideserve` (what we set in Step 2).

**You should see** a `PostgreSQL 16.x on x86_64-conda-linux-gnu ...` line.

---

## Step 4 — Create the project database

Postgres by default has a `postgres` database. Our config expects one called `illiniguideserve`:

```bash
psql -h localhost -p 5432 -U illiniguideserve -d postgres -c "CREATE DATABASE illiniguideserve;"
```

Password again: `illiniguideserve`.

**You should see** `CREATE DATABASE`.

Verify the target DB is reachable:

```bash
psql -h localhost -p 5432 -U illiniguideserve -d illiniguideserve -c "\dt"
```

**You should see** `Did not find any relations.` — that's correct; tables don't exist yet, `scripts.init_db` will create them.

---

## Step 5 — Point the backend at Postgres and initialize tables

Switch back to **Terminal 3** (or open a new one). This one runs the backend, so use the backend venv, **not** the `pg` conda env.

```bash
cd ~/IlliniGuide/backend
source .venv/bin/activate

# tell every backend script and script the same URL
export DATABASE_URL="postgresql+psycopg://illiniguideserve:illiniguideserve@localhost:5432/illiniguideserve"

python -m scripts.init_db
```

**You should see** something like:

```
Creating pgvector extension...
Creating tables...
Done: courses, instructors, gpa_stats, course_chunks, eval_runs, eval_results
```

(The exact output depends on `scripts/init_db.py`. What matters: no traceback.)

Verify with `psql`:

```bash
psql -h localhost -p 5432 -U illiniguideserve -d illiniguideserve -c "\dt"
```

**You should see** all 6 tables listed: `courses`, `instructors`, `gpa_stats`, `course_chunks`, `eval_runs`, `eval_results`.

---

## Step 6 — Ingest real UIUC data

```bash
python -m scripts.ingest_ece_prereqs --limit 80
```

**You should see** a progress log ending with something like `Ingested 80 ECE course rows`. Takes 30 s to a minute (web scrape).

```bash
python -m scripts.ingest_gpa --limit 20
```

**You should see** `Ingested 20 GPA rows from WAF CSV` or similar.

```bash
python -m scripts.seed_career_tags
```

**You should see** `Seeded career tags for 11/12 configured courses. Missing courses: ECE 419` (or similar — the "missing" list depends on whether ECE 419 made it into the 80-row ingestion window).

Spot-check with `psql`:

```bash
psql -h localhost -p 5432 -U illiniguideserve -d illiniguideserve \
  -c "SELECT course_id, title, career_tags FROM courses WHERE course_id IN ('ECE 391','ECE 408','CS 433') ORDER BY course_id;"
```

**You should see** three rows with real titles like `Computer Systems Engineering`, `Applied Parallel Programming` — this is data ingested from the actual ECE website into your database.

---

## Step 7 — Launch the backend with vLLM + Postgres wired in

In the same Terminal 3 (backend venv still active, `DATABASE_URL` still exported):

```bash
export LLM_BACKEND=vllm_remote
export VLLM_BASE_URL=http://localhost:8000
export MODEL_NAME=Qwen/Qwen2.5-7B-Instruct

python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**You should see** `INFO:     Uvicorn running on http://0.0.0.0:8001`.

---

## Step 8 — End-to-end test with real evidence

Open **Terminal 4** in JupyterLab:

```bash
cd ~/IlliniGuide/backend
source .venv/bin/activate

curl -s -X POST http://localhost:8001/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is ECE 391 about?", "debug": true}' \
  | python -m json.tool
```

**You should see** in the response:

- `answer`: a Qwen-generated paragraph that **actually describes** ECE 391 (Computer Systems Engineering, systems programming, low-level C, OS concepts). NOT "insufficient information."
- `citations`: **non-empty array**. At least one entry with `course_id: "ECE 391"` and `source_name`.
- `debug_trace.tool_calls`:
  - `get_course_profile` → `status: "success"`, `result_summary.title: "Computer Systems Engineering"` (or similar)
  - `search_course_docs` → `status: "success"`, `result_summary.n_docs: >= 1`
  - `llm_generate` → `status: "success"`, `arguments.backend: "vllm_remote"`

**If all three tool_calls succeed and citations are non-empty**, Task A is done.

Try a comparison too:

```bash
curl -s -X POST http://localhost:8001/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Compare ECE 408 and CS 433 for AI infra", "debug": true}' \
  | python -m json.tool
```

**You should see** in `used_tools`: `get_course_profile`, `get_course_profile`, `get_gpa_stats`, `get_gpa_stats`, `compare_courses`, `search_course_docs`, `llm_generate` — the full comparison pipeline runs end to end.

---

## Reporting back

Paste back to me:

1. The `answer` field content from Step 8 first query (proves grounded generation).
2. The `citations` array (proves DB retrieval worked).
3. Both `get_course_profile` and `search_course_docs` entries from `debug_trace.tool_calls` (proves tools no longer error).

Then I'll flip Task A to done in project docs and we start C5 (streaming).

---

## Session hygiene (important for ICRN)

ICRN sessions time out at 24 h and long-running Postgres processes stop when your session dies. When you come back tomorrow, before running anything:

```bash
# Terminal 2 (Postgres)
conda activate pg
export PGDATA=$HOME/pgdata
pg_ctl -D $PGDATA -l $PGDATA/server.log -o "-p 5432" start
```

Data in `$PGDATA` **survives** across sessions — you don't lose the ingested courses. You just re-start the Postgres process. `initdb` and `scripts.init_db` and the ingestion scripts are **one-time**; don't re-run them or you'll wipe data.

To cleanly stop Postgres when you're done for the day:

```bash
pg_ctl -D $PGDATA stop
```

---

## Troubleshooting

### `conda: command not found`

The JupyterLab environment did not activate conda. Try:

```bash
source /opt/conda/etc/profile.d/conda.sh
```

Then `conda --version` should work. If not, ping me — we can source-build Postgres but it's more painful.

### `initdb: error: could not access directory "/home/jackj6/pgdata": No such file`

Rare; means `mkdir -p $PGDATA` didn't happen. Do it explicitly:

```bash
mkdir -p $PGDATA
```

Then rerun the `initdb` command.

### `pg_ctl: another server might be running`

You already started Postgres in this session (or a leftover from before). Check:

```bash
pg_ctl -D $PGDATA status
```

If it says running, skip to Step 4. If it says stale PID, remove `$PGDATA/postmaster.pid` and restart.

### `psql: connection to server ... failed: FATAL: password authentication failed`

You typed the wrong password. Restart with the right one (`illiniguideserve` in this guide), or reset via:

```bash
psql -h localhost -p 5432 -U illiniguideserve -d postgres \
     -c "ALTER USER illiniguideserve WITH PASSWORD 'illiniguideserve';"
```

### `init_db` says `psycopg.OperationalError: connection failed`

`DATABASE_URL` isn't exported in the shell running `init_db`, or its value is wrong. Verify:

```bash
echo $DATABASE_URL
```

Should print `postgresql+psycopg://illiniguideserve:illiniguideserve@localhost:5432/illiniguideserve`. If empty, re-export it.

### `init_db` says `extension "vector" is not available`

`pgvector` didn't install into the conda env. Verify:

```bash
ls $HOME/.conda/envs/pg/lib/postgresql/vector.so
```

If missing, reinstall:

```bash
conda install -y -n pg -c conda-forge pgvector
```

Restart Postgres (`pg_ctl -D $PGDATA restart`) and rerun `init_db`.

### `ingest_ece_prereqs` times out fetching the ECE page

ICRN might rate-limit or block outbound HTTP. Retry with a longer delay or a smaller limit:

```bash
python -m scripts.ingest_ece_prereqs --limit 20
```

If ICRN blocks the ECE website, we'd have to bundle a snapshot; ping me if so.

### `/api/chat` still shows `psycopg.OperationalError` after everything

Terminal 3's `uvicorn` was started **before** you exported `DATABASE_URL`, so it read the default and pointed at nowhere. Stop `uvicorn` (`Ctrl-C`), re-export, restart.

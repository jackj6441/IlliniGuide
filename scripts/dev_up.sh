#!/usr/bin/env bash
# Bring up the whole IlliniGuide dev stack on ICRN with one command.
#
# Starts, in order, waiting for each to be ready before starting the next:
#   1. PostgreSQL   (localhost:5432)
#   2. vLLM         (localhost:8000)
#   3. FastAPI      (localhost:8001)
#
# Each service runs in the background with logs redirected to /tmp/*.log.
# Use ./scripts/dev_down.sh to stop everything cleanly.
#
# Usage:
#   bash scripts/dev_up.sh
#
# Prereqs (one-time, see docs/postgres_icrn_setup.md and docs/vllm_setup.md):
#   - conda env "pg" exists with postgres+pgvector
#   - /tmp/jackj6_pgdata has been initialized with initdb
#   - $HOME/IlliniGuide/backend/.venv exists with backend + vllm installed
#   - `python -m scripts.init_db` has already run (tables created)

set -euo pipefail

# -------- Config (edit if paths differ) --------
REPO="${REPO:-$HOME/IlliniGuide}"
BACKEND="$REPO/backend"
PGDATA="${PGDATA:-/tmp/jackj6_pgdata}"
LOGDIR="${LOGDIR:-/tmp}"

VLLM_MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
VLLM_PORT="${VLLM_PORT:-8000}"
PG_PORT="${PG_PORT:-5432}"
BACKEND_PORT="${BACKEND_PORT:-8001}"

# -------- Helpers --------
log()  { printf "\033[36m[dev_up]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[dev_up]\033[0m %s\n" "$*"; }
die()  { printf "\033[31m[dev_up]\033[0m %s\n" "$*"; exit 1; }

wait_for_port() {
    local port=$1 label=$2 timeout=${3:-120} elapsed=0
    log "waiting for $label on port $port (timeout ${timeout}s)..."
    while ! (echo > "/dev/tcp/localhost/$port") 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ "$elapsed" -ge "$timeout" ]; then
            die "$label never came up on port $port after ${timeout}s. See ${LOGDIR}/${label}.log"
        fi
    done
    log "$label ready on port $port (took ${elapsed}s)"
}

port_free() {
    ! (echo > "/dev/tcp/localhost/$1") 2>/dev/null
}

# -------- 1. Postgres --------
log "==== step 1/3: postgres ===="
if port_free "$PG_PORT"; then
    # shellcheck disable=SC1091
    source /opt/conda/etc/profile.d/conda.sh
    conda activate pg
    pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" -o "-p $PG_PORT" start \
        > "$LOGDIR/postgres.log" 2>&1 || warn "pg_ctl start returned non-zero; may already be up"
    conda deactivate
else
    log "port $PG_PORT already in use; assuming postgres is already up"
fi
wait_for_port "$PG_PORT" "postgres" 30

# -------- 2. vLLM --------
log "==== step 2/3: vllm ===="
if port_free "$VLLM_PORT"; then
    cd "$BACKEND"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    nohup vllm serve "$VLLM_MODEL" \
        --host 0.0.0.0 \
        --port "$VLLM_PORT" \
        --dtype float16 \
        --max-model-len 8192 \
        --gpu-memory-utilization 0.85 \
        --enable-prefix-caching \
        > "$LOGDIR/vllm.log" 2>&1 &
    VLLM_PID=$!
    log "vllm PID $VLLM_PID  logs: $LOGDIR/vllm.log"
else
    log "port $VLLM_PORT already in use; assuming vllm is already up"
fi
# vllm startup: model load + torch compile can take 60-120s on first run
wait_for_port "$VLLM_PORT" "vllm" 300

# -------- 3. Backend --------
log "==== step 3/3: backend ===="
export DATABASE_URL="postgresql+psycopg://illiniguideserve:illiniguideserve@localhost:$PG_PORT/illiniguideserve"
export LLM_BACKEND=vllm_remote
export VLLM_BASE_URL="http://localhost:$VLLM_PORT"
export MODEL_NAME="$VLLM_MODEL"

if port_free "$BACKEND_PORT"; then
    cd "$BACKEND"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    nohup python -m uvicorn app.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT" --reload \
        > "$LOGDIR/backend.log" 2>&1 &
    BACKEND_PID=$!
    log "backend PID $BACKEND_PID  logs: $LOGDIR/backend.log"
else
    log "port $BACKEND_PORT already in use; assuming backend is already up"
fi
wait_for_port "$BACKEND_PORT" "backend" 30

# -------- Done --------
printf "\n\033[32m==== all services up ====\033[0m\n"
printf "  postgres  localhost:%s\n" "$PG_PORT"
printf "  vllm      localhost:%s   model=%s\n" "$VLLM_PORT" "$VLLM_MODEL"
printf "  backend   localhost:%s\n" "$BACKEND_PORT"
printf "\nLogs:\n"
printf "  tail -f %s/vllm.log\n" "$LOGDIR"
printf "  tail -f %s/backend.log\n" "$LOGDIR"
printf "  tail -f %s/server.log     (postgres)\n" "$PGDATA"
printf "\nQuick test:\n"
printf "  curl -s -X POST http://localhost:%s/api/chat \\\n" "$BACKEND_PORT"
printf "    -H 'content-type: application/json' \\\n"
printf "    -d '{\"message\":\"What is ECE 391 about?\",\"debug\":true}' \\\n"
printf "    | python -m json.tool\n"
printf "\nStop:\n"
printf "  bash scripts/dev_down.sh\n\n"

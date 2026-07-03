#!/usr/bin/env bash
# Stop the IlliniGuide dev stack cleanly.
#
# Stops in reverse order:
#   1. FastAPI backend (uvicorn)
#   2. vLLM
#   3. PostgreSQL
#
# Safe to run when some services are already down — each step is best-effort
# and never fails the whole script.
#
# Usage:
#   bash scripts/dev_down.sh

set -u

PGDATA="${PGDATA:-/tmp/jackj6_pgdata}"

log() { printf "\033[36m[dev_down]\033[0m %s\n" "$*"; }

# -------- 1. Backend --------
log "stopping backend (uvicorn)..."
if pkill -f "uvicorn.*app.main:app"; then
    log "  backend killed"
else
    log "  backend not running"
fi

# -------- 2. vLLM --------
log "stopping vllm..."
if pkill -f "vllm serve"; then
    # give it a moment to release GPU
    sleep 2
    log "  vllm killed"
else
    log "  vllm not running"
fi

# -------- 3. Postgres --------
log "stopping postgres..."
if [ -d "$PGDATA" ]; then
    # shellcheck disable=SC1091
    source /opt/conda/etc/profile.d/conda.sh 2>/dev/null || true
    conda activate pg 2>/dev/null || true
    if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
        pg_ctl -D "$PGDATA" stop >/dev/null 2>&1 && log "  postgres stopped"
    else
        log "  postgres not running"
    fi
else
    log "  postgres data dir $PGDATA not found; skipping"
fi

log "done."

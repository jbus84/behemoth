#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env" 2>/dev/null || true; set +a
: "${OLLAMA_API_KEY:?OLLAMA_API_KEY not set (add to .env)}"
MODEL="${ERA_GEN_MODEL:-qwen3-coder-next}"
PROMPT="${1:?prompt required}"
curl -sS --max-time 180 https://ollama.com/api/generate \
  -H "Authorization: Bearer $OLLAMA_API_KEY" \
  -d "$(jq -n --arg m "$MODEL" --arg p "$PROMPT" --argjson t "${ERA_GEN_TEMP:-0.7}" '{model:$m, prompt:$p, stream:false, options:{temperature:$t}}')" \
  | jq -r '.response'

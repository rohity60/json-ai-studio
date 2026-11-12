#!/usr/bin/env bash
# Fetch Anna's LLM-friendly docs corpus into a gitignored dir for coding agents to grep.
# Usage: bash apps/web/ai/feature/anna-app/fetch-anna-docs.sh
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
OUT="$ROOT/.anna-docs"
mkdir -p "$OUT"
curl -fsSL https://anna.partners/llms.txt -o "$OUT/llms.txt"
curl -fsSL https://anna.partners/llms-full.txt -o "$OUT/llms-full.txt"
wc -c "$OUT"/*.txt

#!/usr/bin/env bash
# Build the Executa as a self-contained archive for one platform (the one
# this runs on). Anna's Cloud Agent has no project Python, so the plugin
# ships as a PyInstaller --onedir bundle.
#
#   bash build_binary.sh            → dist/json-ai-studio-<version>-<platform>.tar.gz
#
# Archive layout (root): json-ai-studio (launcher), _internal/, manifest.json
set -euo pipefail
cd "$(dirname "$0")"

NAME="json-ai-studio"
VERSION="$(python3 -c 'import json;print(json.load(open("executa.json"))["version"])')"
API_SRC="$(cd ../../../api/src && pwd)"

case "$(uname -s)" in
  Darwin) OS=darwin ;;
  Linux) OS=linux ;;
  *) echo "unsupported OS: $(uname -s)" >&2; exit 2 ;;
esac
case "$(uname -m)" in
  arm64|aarch64) [ "$OS" = darwin ] && ARCH=arm64 || ARCH=aarch64 ;;
  x86_64|amd64) ARCH=x86_64 ;;
  *) echo "unsupported arch: $(uname -m)" >&2; exit 2 ;;
esac
PLATFORM="$OS-$ARCH"

rm -rf build "dist/$NAME"
# --frozen: build exactly what uv.lock pins (an unpinned litellm was ~3x larger).
# tiktoken_ext: litellm's tokenizer plugin is not found by static analysis.
# Excludes: server/DB packages the engine imports nothing from at runtime.
uv run --frozen --with pyinstaller pyinstaller \
  --noconfirm --onedir --strip --name "$NAME" \
  --distpath dist --workpath build --specpath build \
  --paths "$API_SRC" \
  --add-data "$API_SRC/json_ai_studio/config:json_ai_studio/config" \
  --collect-data litellm \
  --collect-submodules json_ai_studio \
  --collect-submodules jstudio \
  --hidden-import tiktoken_ext --hidden-import tiktoken_ext.openai_public \
  --exclude-module botocore --exclude-module boto3 --exclude-module asyncpg \
  --exclude-module uvloop --exclude-module alembic --exclude-module uvicorn \
  --log-level ERROR \
  json_ai_studio_plugin.py

# Data files only; the module itself is imported by litellm at load.
rm -rf "dist/$NAME/_internal/litellm/proxy/_experimental"

cat > "dist/$NAME/manifest.json" <<JSON
{
  "name": "$NAME",
  "version": "$VERSION",
  "runtime": { "binary": { "entrypoint": "$NAME", "permissions": { "$NAME": "0o755" } } }
}
JSON

ARCHIVE="dist/$NAME-$VERSION-$PLATFORM.tar.gz"
tar -czf "$ARCHIVE" -C "dist/$NAME" .
echo "built $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1)), unpacked $(du -sh "dist/$NAME" | cut -f1)"

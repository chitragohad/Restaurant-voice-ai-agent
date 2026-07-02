#!/usr/bin/env bash
# Copy Heritage Tech UI into public/ for Vercel CDN + keep FastAPI on same origin.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATIC="$ROOT/src/server/static"
PUBLIC="$ROOT/public"

rm -rf "$PUBLIC"
mkdir -p "$PUBLIC/static"

cp "$STATIC"/*.html "$PUBLIC/"
cp "$STATIC"/*.css "$STATIC"/*.js "$PUBLIC/static/"

echo "Vercel build: copied UI to public/ ($(find "$PUBLIC" -type f | wc -l | tr -d ' ') files)"

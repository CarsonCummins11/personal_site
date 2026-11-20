#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

uv run render_blog.py

git add -A docs
if git diff --cached --quiet; then
    echo "nothing to commit"
    exit 0
fi
git commit -m "${1:-render blog posts}"
git push origin master
echo "okie dokie!"

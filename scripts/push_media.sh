#!/usr/bin/env bash
# Instagram downloads images (and the Reel, if resumable upload is not used) from a public URL.
# We keep them on a throw-away orphan branch called `media` that is force-pushed on every run,
# so the repository history never grows.
set -euo pipefail

: "${GITHUB_TOKEN:?GITHUB_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

TMP="$(mktemp -d)"
shopt -s nullglob
cp out/*.jpg out/*.mp4 "$TMP"/
cd "$TMP"
git init -q -b media
git config user.name "ig-automation-bot"
git config user.email "ig-automation-bot@users.noreply.github.com"
git add -A
git commit -qm "media for today's post"
git remote add origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git push -q --force origin media
echo "media branch updated"

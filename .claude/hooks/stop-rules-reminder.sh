#!/bin/bash
# .claude/hooks/stop-rules-reminder.sh
# Reminds the user to follow the Stop Checklist before ending a session.
# Set SKIP_STOP_RULES=true to disable this hook entirely.

set -euo pipefail

[[ "${SKIP_STOP_RULES:-}" == "true" ]] && exit 0
[[ -z "${CLAUDE_PROJECT_DIR:-}" ]] && exit 0

# 1. Read JSON input from stdin (needed for stop_hook_active and session_id)
INPUT="$(cat)"
STOP_HOOK_ACTIVE="false"
SESSION_ID_FROM_INPUT=""
if command -v jq >/dev/null 2>&1; then
  STOP_HOOK_ACTIVE="$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo "false")"
  SESSION_ID_FROM_INPUT="$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || echo "")"
else
  echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true' && STOP_HOOK_ACTIVE="true"
  SESSION_ID_FROM_INPUT="$(echo "$INPUT" | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/' || echo "")"
fi

if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
  exit 0
fi

# 2. Repo Check
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
command -v git >/dev/null 2>&1 || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# 3. Robust Hash Helper
hash_it() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  elif command -v md5sum >/dev/null 2>&1; then
    md5sum | awk '{print $1}'
  elif command -v md5 >/dev/null 2>&1; then
    md5 -q
  else
    return 1
  fi
}

# 4. State Logic with Fallback & Strict Sanitization
if ! PROJECT_HASH="$(printf '%s' "$CLAUDE_PROJECT_DIR" | hash_it)"; then
  echo "=== STOP CHECKLIST ===" >&2
  echo "Read and follow the 'Stop Checklist' section in CLAUDE.md." >&2
  exit 2
fi

SESSION_KEY_RAW="${SESSION_ID_FROM_INPUT:-${CLAUDE_SESSION_ID:-$PROJECT_HASH}}"
SESSION_KEY="$(printf '%s' "$SESSION_KEY_RAW" | tr -cd '[:alnum:]_-')"
[[ -z "$SESSION_KEY" ]] && SESSION_KEY="$PROJECT_HASH"

TMPROOT="${TMPDIR:-/tmp}"
[[ ! -d "$TMPROOT" || ! -w "$TMPROOT" ]] && TMPROOT="/tmp"
STATE_FILE="$TMPROOT/claude_rules_${SESSION_KEY}_${UID:-0}.sha"

# Fingerprint: HEAD commit + staged + unstaged + untracked (names AND content)
HEAD_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo "NO_HEAD")"
UNTRACKED_HASHES="$(git ls-files --others --exclude-standard 2>/dev/null | head -100 | while read -r f; do [[ -f "$f" ]] && echo "$f:$(git hash-object "$f" 2>/dev/null || echo ERR)"; done)"
CURRENT_SHA="$( { echo "----HEAD----"; echo "$HEAD_COMMIT"; echo "----DIFF----"; git diff 2>/dev/null; echo "----CACHED----"; git diff --cached 2>/dev/null; echo "----UNTRACKED----"; echo "$UNTRACKED_HASHES"; } | hash_it || echo "NO_SHA" )"
CURRENT_SHA="${CURRENT_SHA:-NO_SHA}"

# If fingerprint matches, we've already reminded for these exact changes in this session
if [[ -f "$STATE_FILE" ]] && [[ "$CURRENT_SHA" == "$(cat "$STATE_FILE")" ]]; then
  exit 0
fi

# 5. Build the reason message
NL=$'\n'
REASON=""
REASON+="STOP CHECKLIST - Read and follow the 'Stop Checklist' section in CLAUDE.md.${NL}"
REASON+="Mark each item: done, or N/A"

# 6. Output JSON to block stopping until checklist is addressed
if command -v jq >/dev/null 2>&1; then
  REASON_JSON=$(printf '%s' "$REASON" | jq -Rs .)
  echo "{\"decision\": \"block\", \"reason\": ${REASON_JSON}}"
else
  REASON_ESCAPED=$(printf '%s' "$REASON" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')
  echo "{\"decision\": \"block\", \"reason\": \"${REASON_ESCAPED}\"}"
fi

# Update state so we don't block again for same fingerprint on next stop attempt
{ TEMP_STATE="$(mktemp "${STATE_FILE}.XXXXXX")" && echo "$CURRENT_SHA" > "$TEMP_STATE" && mv -f "$TEMP_STATE" "$STATE_FILE"; } 2>/dev/null || rm -f "${TEMP_STATE:-}" 2>/dev/null || true
exit 0

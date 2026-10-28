#!/bin/bash
# LCEDA Pro (嘉立创EDA专业版) CLI wrapper.
#
#   eda.sh open <project.eprj2> [headless]   open a project, save its session id to $LCEDA_WORK/sid.txt
#   eda.sh sessions                          list editor sessions
#   eda.sh <file.js> [timeout_s] [args_json] run a JS file in the session; prints {"success","result","error"}
#
# The JS runs as an async function body (top-level await, `return` = result) with these prepended:
#   CFG    contents of $LCEDA_WORK/project.json
#   ARGS   the args_json argument (or {})
#   pcb()  activates the PCB document named in CFG (call it before pcb_* APIs)
# "success": true only means the code ran. Validate the business result yourself (re-read, netlist, DRC).
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=${LCEDA_WORK:-$PWD}
BIN=${LCEDA_BIN:-"/Applications/嘉立创EDA(专业版).app/Contents/MacOS/LCEDA-Pro"}

case "$1" in
  open)
    [ -f "$2" ] || { echo "no such project: $2" >&2; exit 1; }
    out=$("$BIN" open --path "$2" ${3:+--headless true})
    echo "$out"
    sid=$(printf '%s' "$out" | python3 -c '
import sys, json
d = json.load(sys.stdin); v = d.get("value", d)
print(v if isinstance(v, str) else (v.get("sessionId") or v.get("session") or ""))')
    [ -n "$sid" ] && echo "$sid" > "$WORK/sid.txt" && echo "session $sid -> $WORK/sid.txt"
    exit 0 ;;
  sessions)
    "$BIN" session list; exit 0 ;;
esac

SID=${LCEDA_SID:-$(cat "$WORK/sid.txt" 2>/dev/null)}
[ -n "$SID" ] || { echo '{"success":false,"result":null,"error":"no session: run eda.sh open <project> first"}'; exit 1; }
[ -f "$1" ] || { echo "{\"success\":false,\"result\":null,\"error\":\"no such file: $1\"}"; exit 1; }
T=$(( ${2:-120} * 1000 ))
ARGS_JSON=${3:-'{}'}
CFGJSON=$(cat "$WORK/project.json" 2>/dev/null || echo '{}')
F=$(mktemp "${TMPDIR:-/tmp}/eda.XXXXXX")
{
  echo "const CFG=$CFGJSON;"
  echo "const ARGS=${ARGS_JSON};"
  echo "async function pcb(){ if(CFG.pcb_doc) await eda.dmt_EditorControl.activateDocument(CFG.pcb_doc+'@'+CFG.project_uuid); }"
  cat "$1"
} > "$F"
"$BIN" invoke --session "$SID" --code-file "$F" --timeout $T | python3 -c '
import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except ValueError:
    print(json.dumps({"success": False, "result": None, "error": raw[-2000:]})); sys.exit()
print(json.dumps({"success": d.get("ok", False), "result": d.get("value"), "error": d.get("error")}, ensure_ascii=False))'
rm -f "$F"

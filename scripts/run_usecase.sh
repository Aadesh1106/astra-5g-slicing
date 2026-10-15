#!/bin/bash
# Start the whole use case: RYU controller + Mininet topology + QoS queues.
# Usage: sudo bash scripts/run_usecase.sh      (RYU_BIN=/path/to/ryu-manager to override)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RYU_BIN="${RYU_BIN:-ryu-manager}"
mkdir -p "$ROOT/logs"

pkill -f '[r]yu-manager' 2>/dev/null; mn -c >/dev/null 2>&1

echo "== 1. RYU controller =="
$RYU_BIN "$ROOT/src/astra_controller.py" > "$ROOT/logs/ryu.log" 2>&1 &
sleep 3

echo "== 2. Mininet (detached, CLI on fifo) =="
rm -f "$ROOT/mn_fifo"; mkfifo "$ROOT/mn_fifo"
nohup python3 "$ROOT/src/astra_5g_topo.py" < "$ROOT/mn_fifo" > "$ROOT/logs/mn.log" 2>&1 &
( exec 3>"$ROOT/mn_fifo"; sleep 86400 ) &
sleep 8

echo "== 3. QoS queues =="
bash "$ROOT/src/astra_qos.sh" > "$ROOT/logs/qos.log" 2>&1 && echo ok

echo "== 4. Health check =="
bash "$ROOT/scripts/healthcheck.sh"

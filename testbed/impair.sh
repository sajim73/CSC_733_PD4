#!/usr/bin/env bash
# Apply (or clear) tc-netem impairment on every node's egress (RQ1).
# One-way delay D is applied at each sender, so node-to-node RTT = 2*D.
# Usage: sudo ./impair.sh N DELAY_MS JITTER_MS LOSS_PCT   |  sudo ./impair.sh N clear
# Calibrate after every change:  ip netns exec lp0 ping -c 50 10.77.0.2
# STATUS: written for the testbed, not yet executed (see README).
set -euo pipefail
N=${1:?}; D=${2:?}
for i in $(seq 0 $((N-1))); do
  ip netns exec lp$i tc qdisc del dev eth0 root 2>/dev/null || true
  [[ $D == clear ]] && continue
  J=${3:-0}; L=${4:-0}
  args=(delay ${D}ms)
  [[ $J != 0 ]] && args+=(${J}ms distribution normal)
  [[ $L != 0 ]] && args+=(loss ${L}%)
  ip netns exec lp$i tc qdisc add dev eth0 root netem "${args[@]}" limit 100000
done

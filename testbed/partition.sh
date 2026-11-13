#!/usr/bin/env bash
# Isolate a set of node namespaces from all other nodes for SECONDS (RQ2).
# Nodes inside the group can still reach each other. Packets are DROPPED
# (not rejected) so TCP retransmission behaviour matches the model.
# Usage: sudo ./partition.sh SECONDS NODE_IDX [NODE_IDX ...]
# STATUS: written for the testbed, not yet executed (see README).
set -euo pipefail
secs=${1:?}; shift; group=("$@")
src_ok=""; for g in "${group[@]}"; do src_ok+="10.77.0.$((g+1)),"; done; src_ok=${src_ok%,}
for g in "${group[@]}"; do
  ip netns exec lp$g iptables -I INPUT  ! -s $src_ok -j DROP
  ip netns exec lp$g iptables -I OUTPUT ! -d $src_ok -j DROP
done
echo "$(date +%s.%N) partition_start ${group[*]}"
sleep "$secs"
for g in "${group[@]}"; do
  ip netns exec lp$g iptables -D INPUT  ! -s $src_ok -j DROP
  ip netns exec lp$g iptables -D OUTPUT ! -d $src_ok -j DROP
done
echo "$(date +%s.%N) partition_end ${group[*]}"

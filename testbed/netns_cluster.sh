#!/usr/bin/env bash
# Create N network namespaces (lp0..lpN-1) joined by a Linux bridge so that
# Redis Cluster nodes talk over veth links instead of loopback (RQ1/RQ2).
# Usage: sudo ./netns_cluster.sh up N | down N
# Requires: iproute2, CONFIG_NET_NS, CONFIG_VETH, CONFIG_BRIDGE in the MMView kernel.
# STATUS: written for the testbed, not yet executed (see README).
set -euo pipefail
cmd=${1:?up|down}; N=${2:?number of nodes}
BR=lpbr0
if [[ $cmd == up ]]; then
  ip link add $BR type bridge && ip addr add 10.77.0.254/24 dev $BR && ip link set $BR up
  for i in $(seq 0 $((N-1))); do
    ns=lp$i
    ip netns add $ns
    ip link add veth$i type veth peer name eth0 netns $ns
    ip link set veth$i master $BR up
    ip -n $ns addr add 10.77.0.$((i+1))/24 dev eth0
    ip -n $ns link set eth0 up
    ip -n $ns link set lo up
  done
else
  for i in $(seq 0 $((N-1))); do ip netns del lp$i 2>/dev/null || true; done
  ip link del $BR 2>/dev/null || true
fi

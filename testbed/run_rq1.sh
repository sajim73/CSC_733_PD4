#!/usr/bin/env bash
# RQ1 driver (testbed). For each impairment level: build the netns cluster,
# start Redis (authors' build, tag livepatch-128) inside the namespaces using
# their redis-cluster-manager, apply netem, run the authors' patch-benchmark
# with method lazy|eager, collect wf logs, and parse them.
# Each condition is ALSO run without patching (reference) under the same
# impairment so throughput/latency effects are measured against a matched control.
# STATUS: skeleton, not yet executed (see README for the exact authors' commands to slot in).
set -euo pipefail
N=${N:-6}; TRIALS=${TRIALS:-10}
LEVELS=("0 0 0" "1 0 0" "5 0 0" "10 0 0" "25 0 0" "50 0 0" "10 2 0" "10 0 0.1" "10 0 1" "10 2 1")
for trial in $(seq 1 $TRIALS); do
  for lvl in $(printf '%s\n' "${!LEVELS[@]}" | shuf); do          # randomised order
    read -r D J L <<<"${LEVELS[$lvl]}"
    for method in lazy eager; do
      out=results-testbed/rq1/d${D}_j${J}_l${L}/$method/t$trial; mkdir -p "$out"
      sudo ./impair.sh "$N" "$D" "$J" "$L"
      ip netns exec lp0 ping -c 20 -q 10.77.0.2 > "$out/calibration.txt"
      # >>> start cluster + run authors' patch-benchmark with --method $method here <<<
      sudo ./impair.sh "$N" clear
    done
  done
done

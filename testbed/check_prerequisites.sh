#!/usr/bin/env bash
# Read-only inventory for a FUTURE native Redis testbed. This does not certify
# MMView compatibility, start any Redis node, or execute an experiment.
set -u
printf 'NATIVE TESTBED PRECHECK — INFORMATION ONLY (unvalidated workflow)\n'
printf 'Kernel: '; uname -r
printf 'OS: '; uname -s
for cmd in bash git ip tc iptables ping redis-cli taskset; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf 'FOUND  %-12s %s\n' "$cmd" "$(command -v "$cmd")"
  else
    printf 'MISSING %-12s\n' "$cmd"
  fi
done
if [[ -r /proc/config.gz ]] && command -v zcat >/dev/null; then
   zcat /proc/config.gz 2>/dev/null | grep -E '^CONFIG_(NET_NS|VETH|BRIDGE|NET_SCH_NETEM|NETFILTER)=' || true
elif [[ -r /boot/config-$(uname -r) ]]; then
   grep -E '^CONFIG_(NET_NS|VETH|BRIDGE|NET_SCH_NETEM|NETFILTER)=' "/boot/config-$(uname -r)" || true
else
   echo 'Kernel CONFIG flags not readable; manual verification required.'
fi
printf '\nNext steps (NOT performed): validate MMView/WfPatch build, node membership, 16384 slots,\n'
printf 'patched Redis version, workload isolation, logs, and per-trial cleanup.\n'

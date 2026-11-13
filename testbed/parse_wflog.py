"""
Parse the authors' WfPatch/Redis log lines (wf_log in redis-live-patch.patch),
e.g.  [REDIS] [Patch Applied] [<epoch ms>] [<node id>] [<version>] [<method>]
and compute per-version update lag and mixed-version window (activation skew).
wf_time() is CLOCK_REALTIME in ms, so logs from nodes on one host (or on
chrony-synchronised hosts) are directly comparable.
Usage: python parse_wflog.py SUBMIT_TIMES.csv LOG [LOG ...] --expected-nodes nodes.csv > per_version.csv
SUBMIT_TIMES.csv: version,submit_epoch_ms (written by the experiment driver).
STATUS: tested only on synthetic log lines (see README).
"""
import csv
import re
import sys
import argparse
from collections import defaultdict

LINE = re.compile(r"\[REDIS\] \[(Patch Applied|Patch Received|Patch Request|New Patch Registered|Patch Signaled)\]((?: \[[^\]]*\])+)")
# field layout after the event name, from redis-live-patch.patch:
#   Patch Request  [t] [me] [peer] [version]
#   Patch Received [t] [me] [sender] [version] [method]
#   Patch Applied / Patch Signaled / New Patch Registered  [t] [me] [version] [method] ...
VERSION_IDX = {"Patch Request": 3, "Patch Received": 3}


def main():
    parser = argparse.ArgumentParser(description="Compute completeness-aware patch lag from Redis logs")
    parser.add_argument("submit_times", help="CSV with version,submit_epoch_ms")
    parser.add_argument("logs", nargs="+", help="node log files")
    parser.add_argument("--expected-nodes", required=True, help="CSV file with node_id column; required to prevent missing-node false success")
    args = parser.parse_args()
    with open(args.expected_nodes, newline="") as f:
        expected = {r["node_id"].strip() for r in csv.DictReader(f)}
    if not expected or "" in expected:
        parser.error("--expected-nodes must contain nonempty node_id values")
    with open(args.submit_times, newline="") as f:
        submit = {int(r["version"]): float(r["submit_epoch_ms"]) for r in csv.DictReader(f)}
    applied = defaultdict(dict)
    requests = defaultdict(int)
    for path in args.logs:
        for line in open(path, errors="replace"):
            m = LINE.search(line)
            if not m:
                continue
            ev = m.group(1)
            f = re.findall(r"\[([^\]]*)\]", m.group(2))
            t, node, v = float(f[0]), f[1], int(f[VERSION_IDX.get(ev, 2)])
            if ev == "Patch Applied":
                applied[v].setdefault(node, t)
            elif ev == "Patch Request":
                requests[v] += 1
    unexpected = {n for d in applied.values() for n in d} - expected
    if unexpected:
        parser.error(f"log includes unknown node IDs: {sorted(unexpected)}")
    w = csv.writer(sys.stdout)
    w.writerow(["version", "nodes_applied", "nodes_total", "update_lag_ms", "mixed_version_window_ms", "requests"])
    for v in sorted(submit):
        at = applied.get(v, {})
        full = expected.issubset(at)
        lag = (max(at.values()) - submit[v]) if full else float("inf")
        skew = (max(at.values()) - min(at.values())) if full else float("inf")
        w.writerow([v, len(at), len(expected), f"{lag:.3f}", f"{skew:.3f}", requests[v]])


if __name__ == "__main__":
    main()

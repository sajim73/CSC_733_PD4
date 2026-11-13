#!/usr/bin/env python3
"""Optional parameterized exploratory run: never overwrites published results.

This is a *simulation*, not a live Redis test. Generates a per-patch CSV for
one chosen RQ condition; supplied report data remain in results/.
Examples:
 python tools/run_custom.py rq1 --nodes 6 --strategy eager --delay-ms 25 --loss-pct 1 --out custom_rq1.csv
 python tools/run_custom.py rq2 --strategy push_only --outage-s 10 --node-timeout-s 5 --out custom_rq2.csv
 python tools/run_custom.py rq3 --mode controller --nodes 15 --strategy lazy --out custom_rq3.csv
"""
import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sim'))
from livepatch_sim import Cluster  # noqa: E402


def arg_parser():
    p = argparse.ArgumentParser(description='Explore one condition in the Group 2 simulator (not Redis)')
    sub = p.add_subparsers(dest='rq', required=True)
    for name in ('rq1', 'rq2', 'rq3'):
        s = sub.add_parser(name)
        s.add_argument('--seed', type=int, default=0)
        s.add_argument('--patches', type=int, default=10)
        s.add_argument('--strategy', choices=['lazy', 'eager', 'push_only'], default='eager' if name != 'rq3' else 'lazy')
        s.add_argument('--out', required=True, help='output CSV, must not be in the report results directory')
        if name in ('rq1', 'rq3'):
            s.add_argument('--nodes', type=int, choices=[6, 15], default=6)
            s.add_argument('--delay-ms', type=float, default=0.0)
        if name == 'rq1':
            s.add_argument('--jitter-ms', type=float, default=0.0)
            s.add_argument('--loss-pct', type=float, default=0.0)
        if name == 'rq2':
            s.add_argument('--scenario', choices=['replica_unreachable', 'primary_isolated', 'partition_2_nodes'], default='replica_unreachable')
            s.add_argument('--outage-s', type=float, default=5.0)
            s.add_argument('--node-timeout-s', type=float, default=15.0)
            s.add_argument('--inject', choices=['before', 'after'], default='before')
        if name == 'rq3':
            s.add_argument('--mode', choices=['immediate', 'sync', 'controller', 'gossip', 'eventloop'], default='controller')
            s.add_argument('--clock-sigma-ms', type=float, default=0.0)
    return p


def main():
    parser = arg_parser()
    a = parser.parse_args()
    if a.patches < 1 or a.patches > 1000:
        parser.error('--patches must be between 1 and 1000')
    if a.rq in ('rq1', 'rq3') and a.delay_ms < 0:
        parser.error('--delay-ms cannot be negative')
    if a.rq == 'rq1' and (a.jitter_ms < 0 or not 0 <= a.loss_pct <= 100):
        parser.error('jitter must be nonnegative and loss percent 0..100')
    if a.rq == 'rq2' and (a.outage_s <= 0 or a.node_timeout_s <= 0):
        parser.error('outage and node timeout must be positive')
    out = Path(a.out).resolve()
    official = (ROOT/'results').resolve()
    if out == official or official in out.parents:
        parser.error('refusing to write in the official results/ directory')
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.rq == 'rq1':
        c = Cluster(a.nodes, a.strategy, delay=a.delay_ms/1000, jitter=a.jitter_ms/1000, loss=a.loss_pct/100, seed=a.seed)
        start = 5.0
        horizon = start + 3*a.patches + 30
    elif a.rq == 'rq2':
        groups = {'replica_unreachable':frozenset({5}), 'primary_isolated':frozenset({1}), 'partition_2_nodes':frozenset({2,7})}
        c = Cluster(9, a.strategy, seed=a.seed, node_timeout=a.node_timeout_s)
        start = 10.0
        t0 = start - 0.5 if a.inject == 'before' else start + 0.05
        c.net.partitions.append((t0, t0+a.outage_s, groups[a.scenario]))
        horizon = t0+a.outage_s+60+3*a.patches
    else:
        kw = {'sync':a.mode == 'sync', 'dta':a.mode if a.mode in ('controller','gossip','eventloop') else None}
        c = Cluster(a.nodes, a.strategy, delay=a.delay_ms/1000, seed=a.seed, clock_sigma=a.clock_sigma_ms/1000, **kw)
        start = 5.0
        horizon = start + 3*a.patches + 30
    for idx in range(a.patches):
        c.schedule_submit(start + 3*idx, idx+1)
    c.run(horizon)
    rows=[]
    for v in range(1,a.patches+1):
        row={'rq':a.rq,'version':v,'strategy':a.strategy,'seed':a.seed,'lag_s':c.lag(v), 'all_nodes_applied':int(math.isfinite(c.lag(v)))}
        if a.rq=='rq3':row.update({'activation':a.mode,'mixed_version_window_ms':c.skew(v)*1000})
        if a.rq=='rq2':row.update({'scenario':a.scenario,'outage_s':a.outage_s,'node_timeout_s':a.node_timeout_s})
        if a.rq=='rq1':row.update({'nodes':a.nodes,'oneway_delay_ms':a.delay_ms,'loss_pct':a.loss_pct})
        rows.append(row)
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    converged=sum(r['all_nodes_applied'] for r in rows)
    print(f'PASS custom {a.rq} SIMULATION: {len(rows)} patches, {converged} converged; {out}')


if __name__=='__main__':
    main()

"""
Runs the model-based experiments for RQ1-RQ3 and writes CSVs, summary JSON
and figures to ../results.  Usage:  python run_all.py [--quick]
Fully deterministic: every trial uses an explicit seed.
"""
import csv
import json
import math
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from livepatch_sim import Cluster  # noqa: E402

QUICK = "--quick" in sys.argv
# a quick run never overwrites the reported results
OUT = os.path.join(HERE, "..", "results_quick" if QUICK else "results")
SEEDS = range(3 if QUICK else 10)
PATCHES = 10 if QUICK else 30
GAP = 3.0                      # seconds between patches (as in the paper)
WARMUP = 5.0
# lazy = pull (paper's pull); eager = push + always-on pull (paper's push, as implemented
# in the artifact; the paper's recommended hybrid); push_only = eager with pull disabled (ablation)
STRATS = ["lazy", "eager", "push_only"]
SIZES = {6: "3P/1R (6 nodes)", 15: "5P/2R (15 nodes)"}


# ------------------------------------------------------------------ RQ1
def rq1_trial(args):
    n, strat, delay, jitter, loss, seed = args
    c = Cluster(n, strat, delay=delay, jitter=jitter, loss=loss, seed=seed)
    for k in range(PATCHES):
        c.schedule_submit(WARMUP + GAP * k, k + 1)
    c.run(WARMUP + GAP * PATCHES + 30)
    rows = []
    for v in range(1, PATCHES + 1):
        rows.append({"n": n, "strategy": strat, "delay_ms": delay * 1e3, "jitter_ms": jitter * 1e3,
                     "loss_pct": loss * 100, "seed": seed, "version": v, "lag_s": c.lag(v)})
    return rows, dict(c.counters)


def rq1_grid():
    grid = []
    for n in SIZES:
        for strat in STRATS:
            for d in [0.0, 0.001, 0.005, 0.010, 0.025, 0.050]:
                for s in SEEDS:
                    grid.append((n, strat, d, 0.0, 0.0, s))
            for j in [0.0, 0.002]:
                for l in [0.001, 0.01, 0.05]:
                    for s in SEEDS:
                        grid.append((n, strat, 0.010, j, l, s))
                if j:
                    for s in SEEDS:
                        grid.append((n, strat, 0.010, j, 0.0, s))
    return grid


# ------------------------------------------------------------------ RQ2
# 3 primaries x 2 replicas = 9 nodes. Node 0 = primary receiving the patch,
# nodes 0-2 primaries, 3-8 replicas (3,4 -> P0; 5,6 -> P1; 7,8 -> P2).
RQ2_N = 9
SCENARIOS = {
    "none": frozenset(),
    "replica_unreachable": frozenset({5}),
    "primary_isolated": frozenset({1}),
    "partition_2_nodes": frozenset({2, 7}),
}


def rq2_trial(args):
    scen, strat, outage, when, nt, seed, seq = args
    c = Cluster(RQ2_N, strat, seed=seed, node_timeout=nt)
    ts = 10.0
    group = SCENARIOS[scen]
    p_start = ts - 0.5 if when == "before" else ts + 0.05
    p_end = p_start + outage
    if group:
        c.net.partitions.append((p_start, p_end, group))
    versions = [1, 2, 3] if seq else [1]
    for i, v in enumerate(versions):
        c.schedule_submit(ts + 0.5 * i, v)
    horizon = p_end + 60.0
    c.run(horizon)
    healthy = [i for i in range(RQ2_N) if i not in group]
    last = versions[-1]
    healthy_lag = c.lag(last, healthy)
    if group:
        at = c.apply_time.get(last, {})
        iso = [at.get(i, math.inf) for i in group]
        catch = max(iso) - p_end
    else:
        catch = 0.0
    order_ok = all(
        c.apply_time.get(v, {}).get(i, math.inf) <= c.apply_time.get(v + 1, {}).get(i, math.inf)
        for i in range(RQ2_N) for v in versions[:-1])
    return {"scenario": scen, "strategy": strat, "outage_s": outage, "inject": when,
            "node_timeout_s": nt, "seed": seed, "sequence": int(seq),
            "healthy_conv_s": healthy_lag, "isolated_catchup_s": catch,
            "total_lag_s": c.lag(last), "converged": int(c.lag(last) < math.inf),
            "order_ok": int(order_ok), "patch_req": c.counters["PATCH_REQ"],
            "patch_msgs": c.counters["PATCH"], "dup_patch": c.counters["dup_patch"],
            "link_drops": c.counters["link_drops"], "lost_on_drop": c.counters["lost_on_drop"]}


def rq2_grid():
    seeds = range(5 if QUICK else 20)
    grid = []
    for scen in SCENARIOS:
        for strat in STRATS:
            for outage in ([1.0] if scen == "none" else [1.0, 5.0, 10.0]):
                for when in ["before", "after"]:
                    for nt in [15.0, 5.0]:
                        for s in seeds:
                            grid.append((scen, strat, outage, when, nt, s, False))
            if scen != "none":
                for s in seeds:
                    grid.append((scen, strat, 10.0, "before", 15.0, s, True))
    return grid


# ------------------------------------------------------------------ RQ3
def rq3_trial(args):
    n, mode, strat, delay, sigma, seed = args
    kw = {"sync": mode == "sync",
          "dta": mode if mode in ("controller", "gossip", "eventloop") else None}
    c = Cluster(n, strat, delay=delay, seed=seed, clock_sigma=sigma, **kw)
    for k in range(PATCHES):
        c.schedule_submit(WARMUP + GAP * k, k + 1)
    c.run(WARMUP + GAP * PATCHES + 30)
    extra = c.counters["ctrl_msgs"] + c.counters["PONG"]
    return [{"n": n, "mode": mode, "strategy": strat, "delay_ms": delay * 1e3,
             "clock_sigma_ms": sigma * 1e3, "seed": seed, "version": v,
             "lag_s": c.lag(v), "skew_ms": c.skew(v) * 1e3,
             "pong_plus_ctrl_msgs": extra} for v in range(1, PATCHES + 1)]


def rq3_grid():
    grid = []
    for n in SIZES:
        for strat in ["lazy", "eager"]:
            for d in [0.0, 0.001, 0.010]:
                for mode in ["immediate", "sync", "controller", "gossip", "eventloop"]:
                    for sigma in ([0.0, 0.001] if mode == "eventloop" else [0.0]):
                        for s in SEEDS:
                            grid.append((n, mode, strat, d, sigma, s))
    return grid


# ------------------------------------------------------------------ helpers
def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    with Pool() as pool:
        r1 = pool.map(rq1_trial, rq1_grid(), chunksize=4)
        rows1 = [r for rows, _ in r1 for r in rows]
        write_csv(os.path.join(OUT, "rq1_lag.csv"), rows1)
        print("RQ1 rows", len(rows1))
        rows2 = pool.map(rq2_trial, rq2_grid(), chunksize=8)
        write_csv(os.path.join(OUT, "rq2_failures.csv"), rows2)
        print("RQ2 rows", len(rows2))
        r3 = pool.map(rq3_trial, rq3_grid(), chunksize=4)
        rows3 = [r for rows in r3 for r in rows]
        write_csv(os.path.join(OUT, "rq3_activation.csv"), rows3)
        print("RQ3 rows", len(rows3))
    json.dump({"quick": QUICK, "seeds": len(SEEDS), "patches_per_trial": PATCHES},
              open(os.path.join(OUT, "run_meta.json"), "w"), indent=2)


if __name__ == "__main__":
    main()

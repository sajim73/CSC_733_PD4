"""
Smoke test for our package (Section 5.2).  Runs in ~20 s, no arguments:
    cd smoke && python smoke_ours.py
Checks that the model runs, is deterministic, reproduces the paper's
loopback behaviour (calibration), and that the RQ-level claims in Section 3
hold on fresh seeds that were NOT used for the reported results.
Exit code = number of failed checks.
"""
import math
import os
import statistics as st
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
from livepatch_sim import Cluster  # noqa: E402

FRESH = range(100, 104)          # seeds disjoint from run_all.py (0-19)
fails = 0


def check(name, ok, detail=""):
    global fails
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    fails += 0 if ok else 1


def lags(n, strat, **kw):
    out = []
    for s in FRESH:
        c = Cluster(n, strat, seed=s, **kw)
        for k in range(12):
            c.schedule_submit(5 + 3 * k, k + 1)
        c.run(5 + 3 * 12 + 20)
        out += [c.lag(v) for v in range(1, 13)]
    return out


# C1/C2: calibration against the paper's loopback results (pull ~1.5 s median, 0.3-4 s;
# push 0.1-0.2 s; no meaningful dependence on cluster size)
for n in (6, 15):
    lz = lags(n, "lazy")
    check(f"C1 pull median within 1.0-2.5 s, all within 0.3-4 s ({n} nodes)",
          1.0 <= st.median(lz) <= 2.5 and 0.3 <= min(lz) and max(lz) <= 4.0,
          f"median {st.median(lz):.2f}s, range {min(lz):.2f}-{max(lz):.2f}s")
    eg = lags(n, "eager")
    check(f"C2 push lag within 0.1-0.25 s ({n} nodes)", 0.1 <= min(eg) and max(eg) <= 0.25,
          f"range {min(eg)*1e3:.0f}-{max(eg)*1e3:.0f} ms")
e6, e15 = st.median(lags(6, "eager")), st.median(lags(15, "eager"))
check("C3 push lag independent of cluster size (|diff| < 20 ms)", abs(e15 - e6) < 0.02,
      f"{e6*1e3:.0f} vs {e15*1e3:.0f} ms")

# C4 determinism
a, b = lags(6, "lazy"), lags(6, "lazy")
check("C4 identical results for identical seeds", a == b)

# C5 RQ1 claim: added delay increases pull lag more than push lag
lz50, eg50 = st.median(lags(6, "lazy", delay=0.05)), st.median(lags(6, "eager", delay=0.05))
lz0, eg0 = st.median(lags(6, "lazy")), st.median(lags(6, "eager"))
check("C5 50 ms delay: push lag < 0.3 s and pull lag still > 5x push", eg50 < 0.3 and lz50 > 5 * eg50,
      f"pull {lz0:.2f}->{lz50:.2f}s, push {eg0*1e3:.0f}->{eg50*1e3:.0f} ms")


# C6 RQ2 claim: pull repairs an isolated node; push-only cannot once the link is dropped
def isolated(strat, outage=10.0, nt=5.0, seed=0):
    c = Cluster(9, strat, seed=seed, node_timeout=nt)
    c.net.partitions.append((9.5, 9.5 + outage, frozenset({5})))
    c.schedule_submit(10.0, 1)
    c.run(9.5 + outage + 60)
    return c.lag(1), all(c.apply_time[1][i] <= c.apply_time.get(2, {}).get(i, math.inf) for i in c.apply_time[1])


ok_e = all(isolated("eager", seed=s)[0] < math.inf for s in FRESH)
ok_p = all(isolated("push_only", seed=s)[0] == math.inf for s in FRESH)
check("C6 10 s outage, node_timeout 5 s: eager always converges, push-only never does", ok_e and ok_p)


# C7 RQ3 claim: cron-gated activation keeps skew < 1 cron period; event-loop activation < 1 ms
def skew(mode, strat="lazy"):
    out = []
    for s in FRESH:
        c = Cluster(15, strat, seed=s, dta=None if mode == "immediate" else mode)
        for k in range(8):
            c.schedule_submit(5 + 3 * k, k + 1)
        c.run(5 + 3 * 8 + 20)
        out += [c.skew(v) for v in range(1, 9)]
    return out


imm, ctl, evl = skew("immediate"), skew("controller"), skew("eventloop")
check("C7 lazy: immediate skew > 0.3 s; controller DtA < 0.1 s; event-loop DtA < 1 ms",
      st.median(imm) > 0.3 and max(ctl) < 0.1 and max(evl) < 0.001,
      f"median {st.median(imm)*1e3:.0f} / max {max(ctl)*1e3:.0f} / max {max(evl)*1e3:.2f} ms")

# C8 analysis pipeline runs on the shipped results and produces every figure
r = subprocess.run([sys.executable, "analyze.py"], cwd=os.path.join(HERE, "..", "analysis"),
                   capture_output=True, text=True)
res = os.path.join(HERE, "..", "results")
figs = ["fig_rq1_delay.png", "fig_rq1_impair.png", "fig_rq2_catchup.png", "fig_rq3_modes.png", "summary.json"]
check("C8 analyze.py runs and writes all figures + summary.json",
      r.returncode == 0 and all(os.path.exists(os.path.join(res, f)) for f in figs), r.stderr[-200:])

print(f"---- {fails} failed check(s)")
sys.exit(fails)

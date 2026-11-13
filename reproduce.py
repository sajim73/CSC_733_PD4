"""
One command to reproduce every result in Section 3 of our report.

    python reproduce.py           full run (~3-4 min on 12 cores)
    python reproduce.py --quick   short check run (~30 s), writes results_quick/
    python reproduce.py --clean   delete generated results and start fresh

Steps: (1) check dependencies, (2) run the simulation sweeps, (3) run the
analysis, (4) run the smoke test.  Each step is checked and the script stops
at the first failure.  Works on Windows, macOS and Linux.
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
QUICK = "--quick" in sys.argv


def step(name, cmd, cwd, expect=()):
    print(f"\n== {name}")
    t = time.time()
    r = subprocess.run([sys.executable] + cmd, cwd=os.path.join(HERE, cwd))
    missing = [f for f in expect if not os.path.exists(os.path.join(HERE, f))]
    if r.returncode != 0 or missing:
        print(f"FAILED: {name} (exit code {r.returncode}, missing: {missing or 'none'})")
        sys.exit(1)
    print(f"ok ({time.time() - t:.0f} s)")


def main():
    if "--clean" in sys.argv:
        for d in ("results", "results_quick"):
            shutil.rmtree(os.path.join(HERE, d), ignore_errors=True)
        print("removed results/ and results_quick/")
        return

    print("== checking dependencies")
    try:
        import matplotlib, numpy, pandas  # noqa: F401
    except ImportError as e:
        print(f"missing package ({e}); run: python -m pip install -r requirements.txt")
        sys.exit(1)
    print("ok")

    out = "results_quick" if QUICK else "results"
    step("simulation sweeps (RQ1-RQ3)", ["run_all.py"] + (["--quick"] if QUICK else []), "sim",
         [f"{out}/rq1_lag.csv", f"{out}/rq2_failures.csv", f"{out}/rq3_activation.csv"])
    if QUICK:
        print("\nquick run finished; reported results in results/ were not touched")
        return
    step("analysis and figures", ["analyze.py"], "analysis",
         ["results/summary.json", "results/fig_rq1_delay.png", "results/fig_rq2_catchup.png",
          "results/fig_rq3_modes.png"])
    step("smoke test", ["smoke_ours.py"], "smoke")
    print("\nall steps passed; results are in results/")


if __name__ == "__main__":
    main()

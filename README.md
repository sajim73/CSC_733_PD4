# CSC 733 Group 2 — PD4 revised, reproducible simulation artifact

**Project:** *Extending Redis Cluster Live Patching Through Network Realism, Failure Resilience, and Coordinated Activation*  
**Authors:** Gabriel Law, Derek Taylor, Sajim Ahmed  
**Revision date:** 2026-11-12  
**Paper extended:** Fruth and Scherzinger, *Live Patching for Distributed In-Memory Key-Value Stores*, Proceedings of the ACM on Management of Data, 2024, DOI: 10.1145/3698816.  
**External artifact:** https://github.com/sdbs-uni-p/sigmod25-distributed-imkvs-live-patching  
**Reproducibility standard:** https://reproducibility.sigmod.org/

## 1. Read this first:

The validated results in the accompanying PD2 **Section 3** are outputs of **our Python discrete-event simulator**. They are not physical measurements of Redis, WfPatch, a running cluster, or its client performance. Our simulation models version propagation, heartbeats, ordered patch application, network latency/jitter/loss, TCP-style retransmission, temporary partitions and model-based activation protocols. It **does not model client throughput, request latency, failover elections or actual code patch execution**. RQ3's HOLD/ACTIVATE mechanisms are *implemented in the model only*.

**Independent review evidence (Group 1, PD3, 2026-11-04):** on macOS with Python 3.11.18, reviewers ran the full workflow, passed 10 simulation smoke checks, regenerated four figures and obtained exact CSV matches for all three RQs (RQ1 = 23,400 records; RQ2 = 2,580; RQ3 = 21,600). Reviewers also fixed the CRLF line ending of one shell script to pass 16 source-level tests; that defect has been corrected in this package. Pixel-identical PNG rendering was not established and is not claimed.

**Fresh PD4 verification (2026-11-12):** on Linux/Python 3.13.5 with NumPy 2.3.5, pandas 2.2.3 and Matplotlib 3.10.8, `python reproduce.py` finished successfully, passed its 10 simulation checks, and produced all three CSVs matching the byte-level SHA-256 digests of the **original PD2 submission**. Four synthetic parser regressions and quick/custom runs also passed. These exact environment versions are a supplemental verification environment, not the pinned install specification; the frozen requirements below target Python 3.10–3.12. The authors' full-source smoke was **not rerun in this PD4 environment** (it uses network clones); its previously supplied log and the reviewers' repeat check support only source-level checks.

**Boundary:** the optional Linux network-namespace scripts are **unexecuted scaffolds**, and RQ3 Redis source changes are **a design only**. There is no claim that our group reproduced the original paper's throughput, tail latency or native update times on live Redis. The original paper's separately published reproducibility assessment is distinct from our group's evidence.

## 2. Package inventory and status

| Material | Purpose | Evidence/status |
|---|---|---|
| `sim/livepatch_sim.py` | Discrete-event model of patch signaling, dissemination, quiescence, outages, and simulated activation | Simulation code executed |
| `sim/run_all.py` | Fixed, documented RQ1/RQ2/RQ3 experiment grids and seeds | Full simulation executed and peer reproduced |
| `analysis/analyze.py` | Summary tables, IQR/percentiles/bootstrap confidence intervals, 4 PNG charts | Executed; charts regenerated |
| `reproduce.py`, `requirements.txt` | Standard full/quick reproduction command and pinned dependencies | Executed |
| `results/*.csv`, `summary.json`, `fig_*.png`, `run_meta.json` | Submitted model data, analysis, and visual reference results | Complete, generated |
| `reference/sha256_csv.json`, `tools/verify_reference.py` | Original-PD2 CSV fingerprints and exact-match checking | Passed 3/3 exact matches locally |
| `tools/run_custom.py` | CLI for exploratory RQ1/RQ2/RQ3 parameters; never overwrites `results/` | Three example scenarios executed |
| `smoke/smoke_ours.py`, `smoke/smoke_ours.log` | 10 independent-seed assertions for the simulation workflow | All 10 passed |
| `smoke/smoke_authors_artifact.sh`, `smoke/smoke_authors_artifact.log` | Original authors' source-patch checks without executing Redis | Historical source check; reviewers reproduced 16 passes |
| `testbed/parse_wflog.py`, `testbed/test_parser.py`, `expected_nodes_example.csv` | Completeness-aware log parser for future Redis trials; synthetic regression cases | Four synthetic tests passed; native data untested |
| `testbed/netns_cluster.sh`, `impair.sh`, `partition.sh`, `run_rq1.sh` | Planned Redis namespace, impairment and benchmark workflows | **Unexecuted**, RQ1 driver incomplete |
| `testbed/check_prerequisites.sh` | Read-only inventory for future Linux testbed preparation | Script exercised; not a native validation |
| `rq3-design/DESIGN.md` | Future Redis HOLD/ACTIVATE implementation specification | Design, not compiled or tested |
| `LICENSE` | MIT license for Group 2 files | Included; original authors' license applies to original code |

## 3. Isolated simulation setup (supported submission path)

**Verified historical environments:** Windows 11/Python 3.10.11 (Group 2), macOS/Python 3.11.18 (peer group).  
**Pinned install target:** CPython 3.10, 3.11 or 3.12, with the package versions in `requirements.txt` (NumPy 1.26.4, pandas 2.3.1, Matplotlib 3.9.2). Avoid Python 3.13 for *this pinned set*; NumPy 1.26.4 does not support it. A supplemental Python 3.13 run with a *different, available* library set is reported above and in the PD4 verification log. No Docker, root, Redis, modified kernel or network connection is needed for the **Python experiments**. Approximately 1 GB of RAM is adequate, subject to the number of concurrent workers.

**Linux/macOS:** from this `artifact/` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python reproduce.py --quick
python reproduce.py
python tools/verify_reference.py
python testbed/test_parser.py
```

**Windows PowerShell:** from the same directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python reproduce.py --quick
python reproduce.py
python tools/verify_reference.py
python testbed/test_parser.py
```

If PowerShell restricts script activation, you can call `.\.venv\Scripts\python.exe` directly rather than modifying the computer-wide execution policy. Do not confuse the above simulation commands with the Linux-only Redis-native scripts later in this file.

## 4. Reproducing the report's results

- `python reproduce.py --quick` creates only a short set of three CSV files in `results_quick/`, without editing the submitted full results. This is a setup/sanity check, *not* a report figure reproduction.
- `python reproduce.py` performs the full RQ1–RQ3 simulation sweeps, analysis, figure generation and 10 simulation smoke assertions. It overwrites the generated `results/` outputs and stops on errors. On one observed run it took about 85 seconds; time depends on CPU and environment.
- `python tools/verify_reference.py` compares the three regenerated `results/*.csv` files to `reference/sha256_csv.json` from the **original October 14 PD2 submission**, printing `PASS` per file. On a different Python/library/platform, slight byte-level differences may be possible and should be investigated, not mislabeled as automatic scientific falsification.
- `python testbed/test_parser.py` reports four synthetic parser tests. These check correctness of missing-node detection; they **do not** validate actual Redis logs.
- `python reproduce.py --clean` permanently removes `results/` **and** `results_quick/` (including the ZIP's packaged reference figures and CSVs). Use only if you intend to regenerate all outputs; unzip the archive again if needed.

**What signals completion:** full run exits 0 and prints `all steps passed`; `results/` contains three CSV files, four figures, `summary.json` and `run_meta.json`; the smoke step ends `0 failed check(s)`; the verification script prints `REFERENCE CHECK: 3/3 exact CSV matches` when byte-identical. A partial sweep, missing output, nonzero return code or an unvalidated native testbed is not a successful full result.

### Report-to-file map

| Revised PD2 result | Source data | Figure / statistics |
|---|---|---|
| §3.1 / Table 3.1, Figure 3.1 — delay vs. update lag | `results/rq1_lag.csv` | `fig_rq1_delay.png`, `summary.json` `rq1_delay` |
| §3.1 — jitter and packet loss | `results/rq1_lag.csv` | `fig_rq1_impair.png`, `summary.json` `rq1_impair` |
| §3.2 / Table 3.2, Figure 3.2 — outage/catch-up | `results/rq2_failures.csv` | `fig_rq2_catchup.png`, `summary.json` `rq2`, `rq2_sequence` |
| §3.3 / Table 3.3, Figure 3.3 — activation modes | `results/rq3_activation.csv` | `fig_rq3_modes.png`, `summary.json` `rq3_lag`, `rq3_skew`, `rq3_msgs` |

### Optional custom experiments (not part of report data)

`tools/run_custom.py` accepts command-line parameters for one **exploratory simulation** condition per call, with a separate output path. For example:

```bash
python tools/run_custom.py rq1 --nodes 6 --strategy eager --delay-ms 25 --loss-pct 1 --patches 10 --seed 7 --out custom/rq1.csv
python tools/run_custom.py rq2 --scenario replica_unreachable --strategy push_only --outage-s 10 --node-timeout-s 5 --out custom/rq2.csv
python tools/run_custom.py rq3 --nodes 15 --strategy lazy --mode controller --delay-ms 1 --out custom/rq3.csv
```

Run `python tools/run_custom.py --help` and `python tools/run_custom.py rq1 --help` for all supported options. The published multi-factor grid remains fixed in `sim/run_all.py` to preserve the original report's experimental design and output ordering. **Exploratory settings do not revise the published figures or inference.**

## 5. Simulation design and interpretation limits

- **Control flow:** Redis 7.0's cluster maintenance timer and the authors' patched source motivate a 100 ms cronjob cycle, ordered one-version-per-iteration application, headers advertising versions and patch bitmaps, and a five-second request suppression interval.
- **Distribution:** `lazy` means pull; `eager` means push **with pull still active** (the paper's implementation, commonly called hybrid); `push_only` disables pull and is Group 2's model ablation, not an original experimental mode.
- **Networks:** per-transmission one-way delay, jitter and loss with a simplified TCP-style retransmission/backoff model. Real kernel TCP behavior may differ. State size, client traffic, memory/cpu contention and Redis failover elections are not represented.
- **RQ1:** six or fifteen modeled Redis nodes; delay and impairment sweeps. Metrics are update lag and simulated message behavior, not client throughput or response time.
- **RQ2:** nine nodes, outages of 1/5/10 s, partitions before/after patch submission, 5/15-second timeout. Catch-up is relative to the end of isolation. The outage is a *network partition*, not a process crash/restart. No failover or service availability measurements.
- **RQ3:** controller, gossip barrier, sync and event-loop modes exist as model rules. Claims about sub-millisecond skew depend on assumed event-loop timing and clock error; no production Redis software has been modified to execute these proposals.

## 6. Authors' original artifact — limited smoke testing

Historical script, requiring git and Internet access, from `artifact/`:

```bash
bash smoke/smoke_authors_artifact.sh ./_authors
```

The retained log from the original submission records **16 PASS entries**. The reviewers independently ran the script after correcting CRLF line endings and also reported all **16** passing. Tests include repository layout; application of pinned Redis 7.0.11, memtier and kpatch patches; a `clusterCron` quiescence-point call; patch version/bitmap fields; eager transfer; and ordered activation logic. This is **source inspection / patch application**, not direct validation of update lag, latency, throughput or memory. The script now ships with LF endings. It was not rerun with network downloads for this revision.

The upstream authors' full experiments require a modified MMView/WfPatch kernel and special resources (their guidance specifies at least **384 GB RAM**, **700 GB free storage**, **22 CPU cores**, and approximately **130 hours**). Their QEMU VM includes the modified kernel; CPU pinning must still match the target hardware. We did not perform the full native reproduction. See their `reproduction/README.md` for complete hardware and CPU-pinning details.

## 7. Native Redis testbed scaffolds — NOT a validated workflow

The following are future-work *specifications/scaffolds only*. Do not treat any of these commands as successful native experimentation. The optional tools include Linux with MMView/WfPatch kernel support, `bash`, `git`, `iproute2` (`ip`, `tc`), `iptables`, `ping`, `redis-cli`, `taskset`, appropriate Redis benchmarking/build tools, and privileges for namespaces, bridges and network control. Exact kernel/tool version combinations are **not validated**; capture versions and configuration first. A **read-only** inventory helper is `bash testbed/check_prerequisites.sh`.

`testbed/run_rq1.sh` remains **incomplete**: it has a placeholder for starting patched Redis, creating/validating the cluster, running memtier workload/patch commands, and collecting matched controls. `netns_cluster.sh`, `impair.sh` and `partition.sh` are not validated on the target kernel. RQ3 native HOLD/ACTIVATE code has **not been implemented**; its proposed logic is in `rq3-design/DESIGN.md`. Dr. Koh expressly approved addressing the simulation issues and transparently documenting this unexecuted work instead of requiring native reimplementation for PD4.

Before a real Redis study, confirm `CLUSTER INFO` (`cluster_state:ok`), configured node count, full 16,384-slot coverage, binary version, peer connectivity, kernel capabilities, workload/latency capture, warm-up, consistent CPU pinning, matched no-patch controls, clean state and complete expected-node logs. No real-Redis experiment has been run to validate those checks.

The corrected `testbed/parse_wflog.py` requires a manifest of **all expected node IDs** so an unlogged node cannot silently disappear from the sample:

```bash
python testbed/parse_wflog.py submit_times.csv node0.log node1.log \
  --expected-nodes testbed/expected_nodes_example.csv > patch_lags.csv
```

The example CSV is a format illustration only; use the **actual** IDs of every node in the future test cluster. If any expected node lacks an application event, the parser emits `inf` for lag/skew. The parser has synthetic regression coverage but is not yet validated against live logs.

## 8. Reviewer correction log

| Review issue | What changed | Status |
|---|---|---|
| Bash CRLF prevented macOS execution | All `.sh` files shipped with Unix LF line endings | Resolved by byte inspection |
| Python environment could affect other projects | Isolated virtual-environment examples for POSIX/PowerShell | Documented |
| Testbed Redis startup and benchmark missing | Explicitly disclose unfinished placeholder; add read-only prerequisites inventory | **Unimplemented**, approved scope |
| Cluster health/preflight unspecified | Named checks and expected-node list requirement | Documented; not native validated |
| Linux tools and tested/untested paths ambiguous | Dependency inventory + verification boundary | Documented |
| Sweep settings are hardcoded | New optional CLI for one-condition exploratory RQ1–RQ3 simulations | Addressed for exploration; publication grid stays fixed |
| Parser missed fully silent nodes | Require `--expected-nodes`; four synthetic regression cases | Fixed and tested synthetically |
| Setup/run/cleanup indicators unclear | Explicit success criteria and warning for destructive `--clean` | Documented |
| PNG bytes not identical | Explain exact CSV match vs rendered-pixel differences | Clarified; no plot defect reported |
| Dependency and report rebuilding not automatic | Manual venv/pip setup and explicit CSV/plot-to-report map | Partially addressed; DOCX regeneration not automated |
| Native coordinated activation not implemented | Label RQ3 native changes as design, simulation as model | **Unimplemented**, approved scope |

## 9. Licensing and citation

Group 2 files: MIT (see `LICENSE`). Code downloaded from the upstream artifact is subject to its separate license (described in upstream repository). The report cites the original paper, Redis, WfPatch, SIGMOD ARI guidance, and relevant networking references. The revised submission includes its own **point-by-point response to reviewers**; the peer review and instructor approval define the course revision scope, not a claim of native system reproducibility.

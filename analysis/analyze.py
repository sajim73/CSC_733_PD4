"""
Summarises ../results/*.csv into summary tables (summary.json, summary.md) and
figures (fig_*.png).  Usage:  python analyze.py
Statistics: median, IQR, and a 95 % bootstrap CI of the median (2,000
resamples, fixed seed).  Infinite values denote non-convergence and are
reported as a convergence rate instead of being averaged.
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
RNG = np.random.default_rng(733)
LABEL = {"lazy": "Pull (lazy)", "eager": "Push+pull (eager)", "push_only": "Push-only (ablation)"}
COLOR = {"lazy": "#1f77b4", "eager": "#d62728", "push_only": "#7f7f7f"}


def stats(x):
    x = np.asarray(x, dtype=float)
    fin = x[np.isfinite(x)]
    out = {"count": int(len(x)), "converged_pct": 100.0 * len(fin) / len(x) if len(x) else math.nan}
    if len(fin) == 0:
        return {**out, "median": math.inf, "q1": math.inf, "q3": math.inf, "p95": math.inf,
                "ci_lo": math.inf, "ci_hi": math.inf, "max": math.inf}
    boot = np.median(RNG.choice(fin, size=(2000, len(fin)), replace=True), axis=1)
    return {**out, "median": float(np.median(fin)), "q1": float(np.percentile(fin, 25)),
            "q3": float(np.percentile(fin, 75)), "p95": float(np.percentile(fin, 95)),
            "max": float(fin.max()), "ci_lo": float(np.percentile(boot, 2.5)),
            "ci_hi": float(np.percentile(boot, 97.5))}


def summarise(df, keys, col):
    rows = []
    for k, g in df.groupby(keys):
        rows.append({**dict(zip(keys, k if isinstance(k, tuple) else (k,))), **stats(g[col])})
    return pd.DataFrame(rows)


def rq1(summary):
    df = pd.read_csv(os.path.join(RES, "rq1_lag.csv"))
    df["lag_s"] = df["lag_s"].astype(float)
    delay = df[(df.jitter_ms == 0) & (df.loss_pct == 0)]
    s_delay = summarise(delay, ["n", "strategy", "delay_ms"], "lag_s")
    imp = df[df.delay_ms == 10]
    s_imp = summarise(imp, ["n", "strategy", "jitter_ms", "loss_pct"], "lag_s")
    summary["rq1_delay"] = s_delay.to_dict("records")
    summary["rq1_impair"] = s_imp.to_dict("records")

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, n in zip(axes, [6, 15]):
        for st in ["lazy", "eager", "push_only"]:
            g = s_delay[(s_delay.n == n) & (s_delay.strategy == st)].sort_values("delay_ms")
            x = np.arange(len(g))
            ax.plot(x, g["median"], marker="o", color=COLOR[st], label=LABEL[st],
                    linestyle="--" if st == "push_only" else "-")
            ax.fill_between(x, g.q1, g.q3, color=COLOR[st], alpha=0.15)
        ax.set_xticks(np.arange(len(g)), ["loopback"] + [f"{d:g}" for d in g.delay_ms[1:]])
        ax.set_yscale("log")
        ax.set_title(f"{n} nodes")
        ax.set_xlabel("Added one-way delay (ms)")
        ax.grid(alpha=0.3, which="both")
    axes[0].set_ylabel("Update lag (s), median and IQR")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_rq1_delay.png"), dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.8))
    sub = imp[(imp.n == 6)]
    labels, data, colors = [], [], []
    for st in ["lazy", "eager", "push_only"]:
        for (j, l), g in sub[sub.strategy == st].groupby(["jitter_ms", "loss_pct"]):
            labels.append(f"{LABEL[st].split(' ')[0]}\nj{j:g} l{l:g}%")
            data.append(g.lag_s[np.isfinite(g.lag_s)].values)
            colors.append(COLOR[st])
    bp = ax.boxplot(data, patch_artist=True, showfliers=True, flierprops={"markersize": 2})
    for b, c in zip(bp["boxes"], colors):
        b.set_facecolor(c)
        b.set_alpha(0.4)
    ax.set_xticks(range(1, len(labels) + 1), labels, fontsize=6, rotation=90)
    ax.set_yscale("log")
    ax.set_ylabel("Update lag (s)")
    ax.set_title("6 nodes, 10 ms one-way delay: jitter (ms) and loss (%)")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_rq1_impair.png"), dpi=200)
    plt.close(fig)


def rq2(summary):
    df = pd.read_csv(os.path.join(RES, "rq2_failures.csv"))
    for c in ["healthy_conv_s", "isolated_catchup_s", "total_lag_s"]:
        df[c] = df[c].astype(float)
    single = df[df.sequence == 0]
    rows = []
    for k, g in single.groupby(["scenario", "strategy", "outage_s", "inject", "node_timeout_s"]):
        h = stats(g.healthy_conv_s)
        c = stats(g.isolated_catchup_s)
        rows.append(dict(zip(["scenario", "strategy", "outage_s", "inject", "node_timeout_s"], k),
                         healthy_median=h["median"], healthy_p95=h["p95"],
                         catchup_median=c["median"], catchup_p95=c["p95"], catchup_max=c["max"],
                         converged_pct=100 * g.converged.mean(), order_ok_pct=100 * g.order_ok.mean(),
                         link_drops=g.link_drops.mean(), patch_req=g.patch_req.mean(),
                         dup_patch=g.dup_patch.mean()))
    s = pd.DataFrame(rows)
    summary["rq2"] = s.to_dict("records")
    seq = df[df.sequence == 1]
    srows = []
    for k, g in seq.groupby(["scenario", "strategy"]):
        c = stats(g.isolated_catchup_s)
        srows.append({"scenario": k[0], "strategy": k[1], "catchup_median": c["median"],
                      "catchup_max": c["max"], "converged_pct": 100 * g.converged.mean(),
                      "order_ok_pct": 100 * g.order_ok.mean()})
    summary["rq2_sequence"] = srows

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, nt in zip(axes, [15.0, 5.0]):
        g = s[(s.scenario == "replica_unreachable") & (s.inject == "before") & (s.node_timeout_s == nt)]
        for st in ["lazy", "eager", "push_only"]:
            h = g[g.strategy == st].sort_values("outage_s")
            y = h.catchup_median.replace(np.inf, np.nan)
            ax.plot(h.outage_s, y, marker="o", color=COLOR[st], label=LABEL[st],
                    linestyle="--" if st == "push_only" else "-")
            for x, yy, cp in zip(h.outage_s, y, h.converged_pct):
                if cp < 100:
                    ax.annotate(f"{cp:.0f}% conv.", (x, 0.2), fontsize=7, color=COLOR[st], ha="center")
        ax.set_title(f"Replica unreachable, node_timeout = {nt:g} s")
        ax.set_xlabel("Outage duration (s)")
        ax.grid(alpha=0.3, which="both")
    axes[0].set_ylabel("Catch-up after reconnection (s), median")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_rq2_catchup.png"), dpi=200)
    plt.close(fig)


def rq3(summary):
    df = pd.read_csv(os.path.join(RES, "rq3_activation.csv"))
    df["mode_l"] = df["mode"] + np.where(df.clock_sigma_ms > 0, "+clk1ms", "")
    lag = summarise(df, ["n", "strategy", "delay_ms", "mode_l"], "lag_s")
    skew = summarise(df, ["n", "strategy", "delay_ms", "mode_l"], "skew_ms")
    msgs = df.groupby(["n", "strategy", "delay_ms", "mode_l"]).pong_plus_ctrl_msgs.mean().reset_index()
    summary["rq3_lag"] = lag.to_dict("records")
    summary["rq3_skew"] = skew.to_dict("records")
    summary["rq3_msgs"] = msgs.to_dict("records")

    order = ["immediate", "sync", "controller", "gossip", "eventloop", "eventloop+clk1ms"]
    names = ["Immediate\n(artifact)", "Sync\n(artifact)", "DtA\ncontroller", "DtA\ngossip",
             "DtA\nevent-loop", "DtA ev-loop\n1 ms clock err"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    sub = df[(df.n == 15) & (df.delay_ms == 1)]
    for ax, col, ylab in [(axes[0], "skew_ms", "Mixed-version window (ms)"),
                          (axes[1], "lag_s", "Update lag (s)")]:
        w = 0.38
        for i, st in enumerate(["lazy", "eager"]):
            data = [sub[(sub.strategy == st) & (sub.mode_l == m)][col].replace(np.inf, np.nan).dropna()
                    for m in order]
            pos = np.arange(len(order)) + (i - 0.5) * w
            bp = ax.boxplot(data, positions=pos, widths=w * 0.9, patch_artist=True,
                            flierprops={"markersize": 2})
            for b in bp["boxes"]:
                b.set_facecolor(COLOR[st])
                b.set_alpha(0.4)
            ax.plot([], [], color=COLOR[st], label=LABEL[st], linewidth=6, alpha=0.4)
        ax.set_xticks(range(len(order)), names, fontsize=7)
        ax.set_yscale("log")
        ax.set_ylabel(ylab)
        ax.grid(alpha=0.3, axis="y", which="both")
    axes[0].legend(fontsize=8)
    fig.suptitle("15 nodes, 1 ms one-way delay", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_rq3_modes.png"), dpi=200)
    plt.close(fig)


def main():
    summary = {}
    rq1(summary)
    rq2(summary)
    rq3(summary)

    def clean(o):
        if isinstance(o, float) and not math.isfinite(o):
            return "inf"
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return clean(float(o))
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        return o
    json.dump(clean(summary), open(os.path.join(RES, "summary.json"), "w"), indent=1)
    print("wrote summary.json and figures to", os.path.abspath(RES))


if __name__ == "__main__":
    main()

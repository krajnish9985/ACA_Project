

import sys, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LOG = """
Policy              IPC   Speedup   LLC dMPKI   MissRed%   DRAM GB/s    RBhit%      Cyc/tok      Tok/s
lru              0.6078    1.0000      55.378      0.000        8.64    81.062    7.397e+08      5.408
srrip            0.6003    0.9877      55.324      0.098        8.53    78.414    7.490e+08      5.341
hawkeye          0.7047    1.1594      55.168      0.380        9.98    95.687    6.380e+08      6.269
mockingjay       0.6858    1.1283      55.081      0.536        9.70    95.088    6.556e+08      6.101
"""

HIGHLIGHT_BEST = False   

METRICS = [
    ("IPC",       "Instructions Per Cycle (IPC)",  "IPC",                        True,  None),
    ("Speedup",   "Speedup over LRU",              "Speedup (x)",                True,  1.0),
    ("LLC dMPKI", "LLC Demand MPKI",               "Demand misses / kilo-instr", False, None),
    ("MissRed%",  "LLC Miss Reduction vs LRU",     "Miss reduction (%)",         True,  0.0),
    ("DRAM GB/s", "DRAM Bandwidth",                "GB/s",                       None,  None),
    ("RBhit%",    "DRAM Row-Buffer Hit Rate",      "Row-buffer hit (%)",         True,  None),
    ("Cyc/tok",   "Cycles per Token",              "Cycles / token",             False, None),
    ("Tok/s",     "Token Generation Throughput",   "Tokens / second",            True,  None),
]

COLORS = {"lru": "#7f7f7f", "srrip": "#1f77b4", "hawkeye": "#d62728", "mockingjay": "#2ca02c"}


def parse(text):
    lines = [l for l in text.strip().splitlines() if l.strip()]
    header = re.split(r"\s{2,}", lines[0].strip())
    data = {}
    for l in lines[1:]:
        parts = l.split()
        if len(parts) != len(header):
            continue
        data[parts[0]] = dict(zip(header[1:], map(float, parts[1:])))
    return header[1:], data


def ylim_for(vals, ref=None):
    """Always start at 0 so bar heights are proportional to values."""
    lo, hi = min(vals), max(vals)
    if ref is not None:
        lo, hi = min(lo, ref), max(hi, ref)
    lo = min(lo, 0)
    hi = max(hi, 0)
    pad = 0.18 * (hi - lo) if hi != lo else 1   # room for two-line labels
    return lo, hi + pad


def fmt(v):
    if abs(v) >= 1e6:
        return f"{v:.3e}"
    if abs(v) >= 100:
        return f"{v:.1f}"
    return f"{v:.4g}" if abs(v) < 10 else f"{v:.2f}"


def make_plot(col, title, ylabel, better, ref, policies, data, outdir):
    vals = [data[p][col] for p in policies]
    lo, hi = ylim_for(vals, ref)

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    x = np.arange(len(policies))
    bars = ax.bar(x, vals, color=[COLORS.get(p, "#9467bd") for p in policies],
                  edgecolor="black", linewidth=0.8, width=0.6, zorder=3)

    if ref is not None:
        ax.axhline(ref, color="black", linestyle="--", linewidth=1, zorder=2,
                   label="LRU baseline" if col == "Speedup" else "baseline")
        ax.legend(loc="upper left", frameon=False)

    ax.set_ylim(lo, hi)
    span = hi - lo

    base = vals[0]
    for i, (b, v) in enumerate(zip(bars, vals)):
        label = fmt(v)
        if i > 0 and base != 0:
            label += f"\n({(v - base) / abs(base) * 100:+.2f}%)"
        ax.text(b.get_x() + b.get_width() / 2, v + 0.015 * span, label,
                ha="center", va="bottom", fontsize=9, fontweight="bold")

    if HIGHLIGHT_BEST and better is not None:
        best = int(np.argmax(vals) if better else np.argmin(vals))
        bars[best].set_linewidth(2.5)
        bars[best].set_edgecolor("gold")

    arrow = {True: " (higher is better)", False: " (lower is better)", None: ""}[better]
    ax.set_title(title + arrow, fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("LLC replacement policy")
    ax.set_xticks(x)
    ax.set_xticklabels([p.upper() if p == "lru" else p.capitalize() for p in policies])
    ax.grid(axis="y", linestyle=":", alpha=0.6, zorder=0)
    if col == "Cyc/tok":
        ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

    fig.tight_layout()
    safe = re.sub(r"[^A-Za-z0-9]+", "_", col).strip("_")
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(outdir, f"{safe}.{ext}"), dpi=200)
    plt.close(fig)
    print(f"saved {outdir}/{safe}")


def main():
    text = open(sys.argv[1]).read() if len(sys.argv) > 1 else LOG
    outdir = sys.argv[2] if len(sys.argv) > 2 else "plots"
    _, data = parse(text)
    policies = list(data.keys())
    os.makedirs(outdir, exist_ok=True)
    for col, title, ylabel, better, ref in METRICS:
        make_plot(col, title, ylabel, better, ref, policies, data, outdir)


if __name__ == "__main__":
    main()
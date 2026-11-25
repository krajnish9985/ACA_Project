#!/usr/bin/env python3



from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Works on servers/headless machines.
import matplotlib.pyplot as plt
import numpy as np


POLICIES = ["LRU", "SRRIP", "Hawkeye", "Mockingjay"]
EXPERIMENT_NAME = "Experiment"


METRIC_PATTERNS = {
    "instructions": r"^instructions\b",
    "cycles": r"^cycles\s+(?=[\d,])",
    "ipc": r"^ipc\b",
    "speedup": r"^speedup vs lru \(same group\)",
    "llc_mpki": r"^demand mpki\b",
    "llc_miss_latency": r"^avg llc miss latency \(cyc\)",
    "dram_read_row_miss_pct": r"^read row-miss %",
    "dram_reads": r"^reads \(row hit\+miss\)",
    "dram_writes": r"^writes \(row hit\+miss\)",
    "write_mode_cycles": r"^cycles in write mode\b",
    "write_mode_pct": r"^as % of total cycles\b",
    "reads_waiting_cycles": r"^of which reads WAITING \(blocked\)",
    "blocked_pct": r"^blocked as % of total cycles\b",
    "rq_empty_cycles": r"^of which RQ empty \(free time\)",
    "write_mode_entries_queue_full": r"^write-mode entries: queue full\b",
    "write_mode_entries_idle": r"^write-mode entries: idle \(RQ empty\)",
    "write_mode_exits": r"^write-mode exits\b",
    "writes_per_exit": r"^writes completed per exit \(avg\)",
    "discarded_reads": r"^in-flight reads discarded at entry\b",
    "discarded_writes": r"^in-flight writes discarded at exit\b",
    "row_closed_invalid_pct": r"^bank row closed/invalid \(reset or first use\)",
    "row_last_used_write_pct": r"^bank last used by a WRITE\b",
    "row_read_read_conflict_pct": r"^read-read conflict \(different row\)",
    "avg_read_queue_depth": r"^average depth\b",
    "read_queue_depth_le1_pct": r"^% of schedules with depth <= 1\b",
    "read_queue_depth_ge8_pct": r"^% of schedules with depth >= 8\b",
    "timeseries_intervals": r"^intervals\b",
    "timeseries_p10": r"^p10\b",
    "timeseries_median": r"^median\b",
    "timeseries_p90": r"^p90\b",
    "timeseries_max": r"^max\b",
}

COMPILED_PATTERNS = {
    key: re.compile(pattern, re.IGNORECASE)
    for key, pattern in METRIC_PATTERNS.items()
}

NUMBER = re.compile(r"[-+]?(?:\d[\d,]*\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def detect_policies(text: str) -> list[str]:
    """Read policy names from the input header, including optional SRRIP+WB."""
    known = {
        "lru": "LRU",
        "srrip": "SRRIP",
        "hawkeye": "Hawkeye",
        "mockingjay": "Mockingjay",
        "srrip_wb": "SRRIP+WB",
    }
    for line in text.splitlines():
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_+]*", line.lower())
        if "lru" in tokens and "srrip" in tokens and "hawkeye" in tokens:
            policies = [known[t] for t in tokens if t in known]
            if "Mockingjay" in policies:
                return policies
    return ["LRU", "SRRIP", "Hawkeye", "Mockingjay"]


def parse_results(path: Path):
    """Parse labelled metric rows using the detected policy-column count."""
    text = path.read_text(encoding="utf-8", errors="replace")
    policies = detect_policies(text)
    n = len(policies)
    metrics: dict[str, list[float]] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for key, pattern in COMPILED_PATTERNS.items():
            match = pattern.match(line)
            if not match:
                continue
            values = NUMBER.findall(line[match.end():])
            if len(values) >= n:
                metrics[key] = [float(v.replace(",", "")) for v in values[:n]]
            break

    cycle_savings = {}
    cycle_re = re.compile(
        r"^(srrip|hawkeye|mockingjay|srrip_wb)\s+cycles saved\s+"
        r"([-+]?\d[\d,]*)\s*\|\s*read-mode\s+([-+]?\d+(?:\.\d+)?)%"
        r"\s+write-mode\s+([-+]?\d+(?:\.\d+)?)%"
        r"\s*\|\s*write-mode with reads waiting\s+([-+]?\d+(?:\.\d+)?)%",
        re.IGNORECASE,
    )
    display_names = {
        "srrip": "SRRIP", "hawkeye": "Hawkeye",
        "mockingjay": "Mockingjay", "srrip_wb": "SRRIP+WB",
    }
    for raw_line in text.splitlines():
        match = cycle_re.match(raw_line.strip())
        if match:
            policy = display_names[match.group(1).lower()]
            cycle_savings[policy] = {
                "cycles_saved": float(match.group(2).replace(",", "")),
                "read_mode_pct": float(match.group(3)),
                "write_mode_pct": float(match.group(4)),
                "write_mode_waiting_pct": float(match.group(5)),
            }

    return metrics, policies, cycle_savings


def setup():
    plt.rcParams.update({
        "figure.figsize": (9.2, 5.6),
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "font.size": 10.5,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9.5,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "--",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def save(fig, output_dir: Path, filename: str):
    fig.tight_layout()
    fig.savefig(output_dir / filename, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {output_dir / filename}")


def annotate_bars(ax, bars, fmt="{:.2f}", offset=3):
    for bar in bars:
        value = bar.get_height()
        ax.annotate(
            fmt.format(value),
            (bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, offset),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )


def plot_grouped_pair(metrics, output_dir, a_key, b_key,
                      a_title, a_ylabel, b_title, b_ylabel,
                      filename, a_fmt="{:.2f}", b_fmt="{:.2f}",
                      a_ylim=None, b_ylim=None):
    if a_key not in metrics or b_key not in metrics:
        return False

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    bars = axes[0].bar(POLICIES, metrics[a_key], width=0.62)
    axes[0].set_title(a_title)
    axes[0].set_ylabel(a_ylabel)
    if a_ylim:
        axes[0].set_ylim(*a_ylim)
    annotate_bars(axes[0], bars, a_fmt)

    bars = axes[1].bar(POLICIES, metrics[b_key], width=0.62)
    axes[1].set_title(b_title)
    axes[1].set_ylabel(b_ylabel)
    if b_ylim:
        axes[1].set_ylim(*b_ylim)
    annotate_bars(axes[1], bars, b_fmt)

    fig.suptitle(EXPERIMENT_NAME + ": " + filename.replace("_", " ").replace(".png", ""),
                 fontsize=14)
    save(fig, output_dir, filename)
    return True


def plot_write_mode(metrics, output_dir):
    required = ["reads_waiting_cycles", "rq_empty_cycles"]
    if not all(k in metrics for k in required):
        return False

    blocked = np.array(metrics["reads_waiting_cycles"]) / 1e6
    idle = np.array(metrics["rq_empty_cycles"]) / 1e6

    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    ax.bar(POLICIES, blocked, width=0.62,
           label="Reads waiting (blocked)")
    ax.bar(POLICIES, idle, width=0.62, bottom=blocked,
           label="Read queue empty (idle/free time)")

    for i in range(len(POLICIES)):
        ax.text(i, blocked[i] / 2, f"{blocked[i]:.2f}",
                ha="center", va="center", fontsize=8)
        ax.text(i, blocked[i] + idle[i] / 2, f"{idle[i]:.2f}",
                ha="center", va="center", fontsize=8)

    ax.set_title("DRAM Write-Mode Cycle Breakdown")
    ax.set_ylabel("Cycles (millions)")
    ax.legend()
    save(fig, output_dir, f"{EXPERIMENT_NAME}_write_mode_breakdown.png")
    return True


def plot_row_miss_reasons(metrics, output_dir):
    keys = [
        "row_closed_invalid_pct",
        "row_last_used_write_pct",
        "row_read_read_conflict_pct",
    ]
    if not all(k in metrics for k in keys):
        return False

    labels = [
        "Bank row closed / invalid",
        "Bank last used by write",
        "Read-read conflict",
    ]
    arrays = [np.array(metrics[k]) for k in keys]

    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    bottom = np.zeros(len(POLICIES))
    for values, label in zip(arrays, labels):
        ax.bar(POLICIES, values, bottom=bottom, width=0.62, label=label)
        bottom += values

    ax.set_title("Reasons for DRAM Read Row Misses")
    ax.set_ylabel("Share of read row misses (%)")
    ax.set_ylim(0, 110)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    save(fig, output_dir, f"{EXPERIMENT_NAME}_row_miss_reasons.png")
    return True


def plot_discarded_requests(metrics, output_dir):
    keys = ["discarded_reads", "discarded_writes"]
    if not all(k in metrics for k in keys):
        return False

    x = np.arange(len(POLICIES))
    width = 0.35
    reads = np.array(metrics[keys[0]]) / 1000
    writes = np.array(metrics[keys[1]]) / 1000

    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    b1 = ax.bar(x - width / 2, reads, width, label="In-flight reads discarded")
    b2 = ax.bar(x + width / 2, writes, width, label="In-flight writes discarded")
    ax.set_xticks(x, POLICIES)
    ax.set_title("In-Flight DRAM Requests Discarded")
    ax.set_ylabel("Discarded requests (thousands)")
    ax.legend()
    annotate_bars(ax, b1, "{:.1f}K")
    annotate_bars(ax, b2, "{:.1f}K")
    save(fig, output_dir, f"{EXPERIMENT_NAME}_discarded_requests.png")
    return True


def plot_single_metric(metrics, output_dir, key, title, ylabel,
                       filename, divisor=1.0, fmt="{:.2f}", ylim=None):
    if key not in metrics:
        return False

    values = np.array(metrics[key], dtype=float) / divisor
    fig, ax = plt.subplots(figsize=(8.8, 5.3))
    bars = ax.bar(POLICIES, values, width=0.62)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(*ylim)
    annotate_bars(ax, bars, fmt)
    save(fig, output_dir, filename)
    return True


def plot_cycle_savings(cycle_savings, output_dir):
    if not cycle_savings:
        return False
    labels = [p for p in ["SRRIP", "Hawkeye", "Mockingjay", "SRRIP+WB"]
              if p in cycle_savings]
    read = np.array([cycle_savings[p]["read_mode_pct"] for p in labels])
    write = np.array([cycle_savings[p]["write_mode_pct"] for p in labels])
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(9.0, 5.5))
    ax.bar(x, read, width=0.62, label="Read-mode cycle savings")
    ax.bar(x, write, width=0.62, bottom=read,
           label="Write-mode cycle savings")
    for i in range(len(labels)):
        ax.text(i, read[i] / 2, f"{read[i]:.1f}%",
                ha="center", va="center", fontsize=9)
        ax.text(i, read[i] + write[i] / 2, f"{write[i]:.1f}%",
                ha="center", va="center", fontsize=9)
    ax.set_xticks(x, labels)
    ax.set_title("Source of Cycle Savings Relative to LRU")
    ax.set_ylabel("Share of cycles saved (%)")
    ax.set_ylim(0, 110)
    ax.legend()
    save(fig, output_dir, f"{EXPERIMENT_NAME}_cycle_savings_source.png")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate cache/DRAM experiment plots from a text results file."
    )
    parser.add_argument(
        "-i", "--input", required=True, type=Path,
        help="Path to the plain-text experiment results file."
    )
    parser.add_argument(
        "-o", "--output", required=True, type=Path,
        help="Directory in which plots will be saved."
    )
    parser.add_argument(
        "--experiment", default=None,
        help="Experiment label used in plot titles and filenames "
             "(default: first part of the input filename, e.g. E1)."
    )
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input file does not exist: {args.input}")

    args.output.mkdir(parents=True, exist_ok=True)
    setup()

    global POLICIES, EXPERIMENT_NAME
    metrics, detected_policies, cycle_savings = parse_results(args.input)
    POLICIES = detected_policies
    EXPERIMENT_NAME = args.experiment or args.input.stem.split("_")[0].upper()
    if not metrics:
        raise SystemExit(
            "No recognized metric rows were found. Check that the input "
            "contains the labelled table rows from the experiment output."
        )

    print(f"Read: {args.input}")
    print(f"Detected policies ({len(POLICIES)}): {', ' .join(POLICIES)}")
    print(f"Extracted {len(metrics)} metric rows:")
    for key, values in metrics.items():
        print(f"  {key}: {values}")
    print(f"Extracted cycle-savings rows: {len(cycle_savings)}")

    generated = []

    # Performance
    if plot_grouped_pair(
        metrics, args.output,
        "ipc", "speedup",
        "Instructions Per Cycle", "IPC",
        "Speedup Relative to LRU", "Speedup (×)",
        f"{EXPERIMENT_NAME}_performance.png",
        a_fmt="{:.4f}", b_fmt="{:.4f}×",
    ):
        generated.append("performance")

    # LLC behavior
    if plot_grouped_pair(
        metrics, args.output,
        "llc_mpki", "llc_miss_latency",
        "LLC Demand MPKI", "Misses per 1000 instructions",
        "Average LLC Miss Latency", "Latency (cycles)",
        f"{EXPERIMENT_NAME}_llc_behavior.png",
        a_fmt="{:.3f}", b_fmt="{:.2f}",
    ):
        generated.append("LLC behavior")

    # DRAM activity
    if plot_grouped_pair(
        metrics, args.output,
        "dram_read_row_miss_pct", "dram_writes",
        "DRAM Read Row-Miss Rate", "Row misses (%)",
        "DRAM Writes Completed", "Writes",
        f"{EXPERIMENT_NAME}_dram_activity.png",
        a_fmt="{:.2f}%", b_fmt="{:,.0f}",
    ):
        generated.append("DRAM activity")

    if plot_write_mode(metrics, args.output):
        generated.append("write-mode breakdown")

    if plot_row_miss_reasons(metrics, args.output):
        generated.append("row-miss reasons")

    if plot_discarded_requests(metrics, args.output):
        generated.append("discarded requests")

    if plot_cycle_savings(cycle_savings, args.output):
        generated.append("cycle savings source")

    if plot_single_metric(
        metrics, args.output,
        "write_mode_pct", "Cycles Spent in DRAM Write Mode",
        "Share of total cycles (%)", f"{EXPERIMENT_NAME}_write_mode_percentage.png",
        fmt="{:.2f}%",
    ):
        generated.append("write-mode percentage")

    if plot_single_metric(
        metrics, args.output,
        "writes_per_exit", "Average DRAM Writes Completed per Write-Mode Exit",
        "Writes per exit", f"{EXPERIMENT_NAME}_writes_per_exit.png",
        fmt="{:.2f}",
    ):
        generated.append("writes per exit")

    print(f"\nGenerated {len(generated)} plot group(s):")
    for name in generated:
        print(f"  - {name}")

    if not generated:
        print("No plots generated: recognized metrics were insufficient.")


if __name__ == "__main__":
    main()

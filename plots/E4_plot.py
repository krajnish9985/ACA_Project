
import os
import re
import argparse
import matplotlib.pyplot as plt
import numpy as np

POLICIES = ["LRU", "SRRIP", "Hawkeye", "Mockingjay"]


def extract_row(filename, label):
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().strip("|").strip()

            if line.lower().startswith(label.lower()):
                remainder = line[len(label):]

                numbers = re.findall(
                    r"[-+]?\d[\d,]*(?:\.\d+)?",
                    remainder
                )

                if len(numbers) >= 4:
                    return [
                        float(x.replace(",", ""))
                        for x in numbers[:4]
                    ]

    raise ValueError(f"Could not find metric: {label}")


def save_bar(output_dir, filename, title, values,
             ylabel, fmt="{:.3f}", baseline=None):

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(POLICIES, values)

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

    if baseline is not None:
        ax.axhline(baseline, linestyle="--", linewidth=1)

    for bar, value in zip(bars, values):
        ax.annotate(
            fmt.format(value),
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=9
        )

    fig.tight_layout()
    path = os.path.join(output_dir, filename)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"Generated: {filename}")


def save_stacked_bar(output_dir, filename, title,
                     labels, series, ylabel):

    x = np.arange(len(labels))
    bottom = np.zeros(len(labels))

    fig, ax = plt.subplots(figsize=(8, 5))

    for name, values in series:
        ax.bar(x, values, bottom=bottom, label=name)
        bottom += np.array(values)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

    fig.tight_layout()
    path = os.path.join(output_dir, filename)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"Generated: {filename}")


def plot_timeseries_distribution(input_file, output_dir):

    p10 = extract_row(input_file, "p10")
    median = extract_row(input_file, "median")
    p90 = extract_row(input_file, "p90")

    x = np.arange(len(POLICIES))
    width = 0.24

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(x - width, p10, width, label="P10")
    ax.bar(x, median, width, label="Median")
    ax.bar(x + width, p90, width, label="P90")

    ax.set_xticks(x)
    ax.set_xticklabels(POLICIES)
    ax.set_ylabel("Read row-miss rate (%)")
    ax.set_title("E4: Row-Miss Rate Distribution Across Intervals")

    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

    fig.tight_layout()
    filename = "E4_row_miss_timeseries_distribution.png"
    fig.savefig(
        os.path.join(output_dir, filename),
        dpi=300,
        bbox_inches="tight"
    )
    plt.close(fig)

    print(f"Generated: {filename}")


def main():

    parser = argparse.ArgumentParser(
        description="Generate E4 cache-policy experiment plots"
    )

    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", required=True)

    args = parser.parse_args()

    input_file = args.input
    output_dir = args.output

    os.makedirs(output_dir, exist_ok=True)

  
    save_bar(
        output_dir,
        "E4_IPC.png",
        "E4: Instructions Per Cycle",
        extract_row(input_file, "IPC"),
        "IPC",
        "{:.4f}"
    )

  
    save_bar(
        output_dir,
        "E4_speedup.png",
        "E4: Speedup Relative to LRU",
        extract_row(input_file, "speedup vs LRU (same group)"),
        "Speedup (x)",
        "{:.4f}",
        baseline=1.0
    )

    
    save_bar(
        output_dir,
        "E4_demand_mpki.png",
        "E4: LLC Demand MPKI",
        extract_row(input_file, "demand MPKI"),
        "Demand MPKI",
        "{:.3f}"
    )

   
    save_bar(
        output_dir,
        "E4_llc_miss_latency.png",
        "E4: Average LLC Miss Latency",
        extract_row(input_file, "avg LLC miss latency (cyc)"),
        "Latency (cycles)",
        "{:.2f}"
    )

   
    save_bar(
        output_dir,
        "E4_read_row_miss.png",
        "E4: DRAM Read Row-Miss Rate",
        extract_row(input_file, "read row-miss %"),
        "Read row-miss (%)",
        "{:.2f}"
    )

  
    blocked = extract_row(
        input_file,
        "of which reads WAITING (blocked)"
    )

    rq_empty = extract_row(
        input_file,
        "of which RQ empty (free time)"
    )

    save_stacked_bar(
        output_dir,
        "E4_write_mode_breakdown.png",
        "E4: DRAM Write-Mode Cycle Breakdown",
        POLICIES,
        [
            ("Reads waiting (blocked)", blocked),
            ("Read queue empty", rq_empty)
        ],
        "Cycles"
    )

 
    save_bar(
        output_dir,
        "E4_write_mode_percentage.png",
        "E4: Time Spent in DRAM Write Mode",
        extract_row(input_file, "as % of total cycles"),
        "Total cycles (%)",
        "{:.2f}"
    )

    save_bar(
        output_dir,
        "E4_discarded_writes.png",
        "E4: In-Flight Writes Discarded at Write-Mode Exit",
        extract_row(input_file, "in-flight writes discarded at exit"),
        "Discarded writes",
        "{:,.0f}"
    )

    save_stacked_bar(
        output_dir,
        "E4_row_miss_reasons.png",
        "E4: Causes of DRAM Read Row Misses",
        POLICIES,
        [
            (
                "Bank row closed/invalid",
                extract_row(
                    input_file,
                    "bank row closed/invalid (reset or first use)"
                )
            ),
            (
                "Bank last used by a write",
                extract_row(
                    input_file,
                    "bank last used by a WRITE"
                )
            ),
            (
                "Read-read conflict",
                extract_row(
                    input_file,
                    "read-read conflict (different row)"
                )
            )
        ],
        "Share of read row-misses (%)"
    )

   
    plot_timeseries_distribution(input_file, output_dir)

    print("\nAll E4 plots generated successfully.")


if __name__ == "__main__":
    main()

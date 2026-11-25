
import os
import re
import argparse
import matplotlib.pyplot as plt

POLICIES = ["LRU", "Hawkeye", "Mockingjay", "SRRIP"]


def extract_wmstat(filename):
    with open(filename, "r") as f:
        lines = [
            line for line in f
            if "WMSTAT cycles" in line
        ]

    if not lines:
        raise ValueError(f"WMSTAT cycles not found in {filename}")

    line = lines[-1]

    pattern = (
        r"WMSTAT cycles\s+total:\s*([\d,]+)"
        r"\s+WQ_nonempty:\s*([\d,]+)"
    )

    match = re.search(pattern, line)

    if not match:
        raise ValueError(f"Could not parse WMSTAT line:\n{line}")

    total_cycles = int(match.group(1).replace(",", ""))
    wq_nonempty = int(match.group(2).replace(",", ""))

    return total_cycles, wq_nonempty


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--lru", required=True)
    parser.add_argument("--hawkeye", required=True)
    parser.add_argument("--mockingjay", required=True)
    parser.add_argument("--srrip", default=None)
    parser.add_argument("--output", "-o", default="E5/")

    args = parser.parse_args()

    files = {
        "LRU": args.lru,
        "Hawkeye": args.hawkeye,
        "Mockingjay": args.mockingjay,
    }

    if args.srrip:
        files["SRRIP"] = args.srrip

    policies = list(files.keys())
    percentages = []

    print("\nWrite queue non-empty fractions:\n")

    for policy, filename in files.items():
        total, nonempty = extract_wmstat(filename)
        percentage = (nonempty / total) * 100
        percentages.append(percentage)

        print(
            f"{policy:12s}: "
            f"{nonempty:,} / {total:,} = {percentage:.2f}%"
        )

    os.makedirs(args.output, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 5))

    bars = ax.bar(policies, percentages)

    ax.set_title(
        "E5: Fraction of Cycles with Write Queue Non-Empty"
    )
    ax.set_ylabel("Cycles with WQ non-empty (%)")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

    for bar, value in zip(bars, percentages):
        ax.annotate(
            f"{value:.2f}%",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center"
        )

    fig.tight_layout()

    output_file = os.path.join(
        args.output,
        "E5_write_queue_nonempty_fraction.png"
    )

    fig.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"\nPlot saved to: {output_file}")


if __name__ == "__main__":
    main()


import os
import argparse
import matplotlib.pyplot as plt
import numpy as np

# H5 experiment values
labels = [
    "SRRIP",
    "SRRIP + WB rule"
]

ipc = [
    0.5992,
    0.5995
]

idle_episodes = [
    4.36,
    4.34
]


def main():

    parser = argparse.ArgumentParser(
        description="H5: SRRIP writeback rule comparison"
    )

    parser.add_argument(
        "--output", "-o",
        default="H5/",
        help="Output directory"
    )

    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    # -------------------------
    # Plot 1: IPC comparison
    # -------------------------

    bars = axes[0].bar(labels, ipc)

    axes[0].set_title("IPC Comparison")
    axes[0].set_ylabel("Instructions Per Cycle")
    axes[0].set_ylim(0.59, 0.61)
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].set_axisbelow(True)

    for bar, value in zip(bars, ipc):
        axes[0].annotate(
            f"{value:.4f}",
            (bar.get_x() + bar.get_width()/2, bar.get_height()),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center"
        )

    # -------------------------
    # Plot 2: Idle episodes
    # -------------------------

    bars = axes[1].bar(labels, idle_episodes)

    axes[1].set_title("DRAM Idle Episodes")
    axes[1].set_ylabel("Idle Episodes (Millions)")
    axes[1].set_ylim(4.2, 4.5)
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].set_axisbelow(True)

    for bar, value in zip(bars, idle_episodes):
        axes[1].annotate(
            f"{value:.2f}M",
            (bar.get_x() + bar.get_width()/2, bar.get_height()),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center"
        )

    fig.suptitle(
        "H5: Effect of Hawkeye/Mockingjay Writeback Rule on SRRIP",
        fontsize=13
    )

    fig.tight_layout()

    output_file = os.path.join(
        args.output,
        "H5_srrip_writeback_comparison.png"
    )

    fig.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"Plot saved to: {output_file}")


if __name__ == "__main__":
    main()


import re
from pathlib import Path

import matplotlib.pyplot as plt

# Paths
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "E6"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "LRU": BASE_DIR / "e1_lru.txt",
    "Mockingjay": BASE_DIR / "e1_mockingjay.txt",
}



def extract_writes(path):
    text = path.read_text(errors="ignore")

    match = re.search(
        r"\bwrites_completed:\s*([\d,]+)",
        text,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            f"Could not find writes_completed counter in {path}"
        )

    return int(match.group(1).replace(",", ""))

def main():
    writes = {
        policy: extract_writes(path)
        for policy, path in FILES.items()
    }

    lru = writes["LRU"]
    mockingjay = writes["Mockingjay"]

    ratio = lru / mockingjay
    reduction = (1 - mockingjay / lru) * 100

    labels = ["LRU", "Mockingjay"]
    values = [lru / 1e3, mockingjay / 1e3]

    fig, ax = plt.subplots(figsize=(8, 5))

    bars = ax.bar(labels, values, width=0.5)

    ax.set_title(
        "DRAM Writes: LRU vs Mockingjay",
        fontsize=14,
        fontweight="bold"
    )

    ax.set_ylabel("DRAM Writes (thousands)")
    ax.set_xlabel("LLC Replacement Policy")

    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    for bar, value, count in zip(bars, values, [lru, mockingjay]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{count:,}",
            ha="center",
            va="bottom",
            fontsize=11
        )

    ax.text(
        0.5, 0.93,
        f"Mockingjay generates {ratio:.2f}x fewer writes ({reduction:.1f}% reduction)",
        transform=ax.transAxes,
        ha="center",
        fontsize=10,
        fontweight="bold"
    )

    ax.set_ylim(0, max(values) * 1.2)

    plt.tight_layout()

    output_file = OUTPUT_DIR / "H6_LRU_vs_Mockingjay_writes.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"LRU writes:        {lru:,}")
    print(f"Mockingjay writes: {mockingjay:,}")
    print(f"Write reduction:   {reduction:.2f}%")
    print(f"Ratio:             {ratio:.2f}x")
    print(f"Plot saved:        {output_file}")


if __name__ == "__main__":
    main()

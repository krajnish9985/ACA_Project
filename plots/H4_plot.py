
import os
import matplotlib.pyplot as plt

# Five comparison groups
policies = [
    "LRU\n(Baseline)",
    "LRU\n(Idle Write Mode\nDisabled)",
    "SRRIP",
    "Hawkeye",
    "Mockingjay"
]


closed_row_share = [
    3.15,   
    3.2,    
    5.85,   
    5.89,   
    1.79    
]



discarded_writes = [
    0.293727,  
    0.29,      
    0.271532,  
    0.202758,  
    0.076709   
]


def make_bar_plot(values, title, ylabel, filename,
                  output_dir, labels, value_format,
                  ylim=None):

    fig, ax = plt.subplots(figsize=(10, 5.5))

    bars = ax.bar(labels, values, width=0.6)

    ax.set_title(title, fontsize=13)
    ax.set_ylabel(ylabel, fontsize=11)

    if ylim:
        ax.set_ylim(ylim)

    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

    for bar, value in zip(bars, values):
        ax.annotate(
            value_format.format(value),
            (
                bar.get_x() + bar.get_width() / 2,
                bar.get_height()
            ),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            fontsize=9
        )

    ax.tick_params(axis="x", labelsize=9)

    fig.tight_layout()

    path = os.path.join(output_dir, filename)

    fig.savefig(
        path,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)

    print(f"Generated: {path}")


def main():

    output_dir = "H4"
    os.makedirs(output_dir, exist_ok=True)

   
    make_bar_plot(
        values=closed_row_share,
        title="H4: Closed/Invalid DRAM Row-Miss Share",
        ylabel="Share of Read Row-Misses (%)",
        filename="H4_closed_row_miss_comparison.png",
        output_dir=output_dir,
        labels=policies,
        value_format="{:.2f}%",
        ylim=(0, 8)
    )


    make_bar_plot(
        values=discarded_writes,
        title="H4: In-Flight Writes Discarded",
        ylabel="Discarded Writes (Millions)",
        filename="H4_discarded_writes_comparison.png",
        output_dir=output_dir,
        labels=policies,
        value_format="{:.3f}M",
        ylim=(0, 0.35)
    )

    print("\nBoth H4 plots generated successfully.")


if __name__ == "__main__":
    main()

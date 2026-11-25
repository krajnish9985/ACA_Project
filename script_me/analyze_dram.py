#!/usr/bin/env python3

import re, sys, os, argparse, statistics

POLS = ["lru", "srrip", "hawkeye", "mockingjay", "srrip_wb"]


def rx(pat, t, cast=float, default=None, flags=re.M):
    m = re.search(pat, t, flags)
    return cast(m.group(1)) if m else default


def parse(path):
    t = open(path).read()
    d = {"path": path}
    m = re.search(r"CPU 0 cumulative IPC: ([\d.]+) instructions: (\d+) cycles: (\d+)", t)
    if not m:
        d["incomplete"] = True
        return d
    d["ipc"], d["instr"], d["cycles"] = float(m[1]), int(m[2]), int(m[3])

    def trip(name):
        m = re.search(name + r"\s+ACCESS:\s+(\d+)\s+HIT:\s+(\d+)\s+MISS:\s+(\d+)", t)
        return tuple(map(int, m.groups())) if m else (0, 0, 0)

    ld, rfo = trip("LLC LOAD"), trip("LLC RFO")
    d["dem_mpki"] = (ld[2] + rfo[2]) / d["instr"] * 1000
    d["llc_miss_lat"] = rx(r"LLC AVERAGE MISS LATENCY:\s+([\d.]+)", t)

    m = re.search(r"RQ ROW_BUFFER_HIT:\s+(\d+)\s+ROW_BUFFER_MISS:\s+(\d+)", t)
    d["rd_hit"], d["rd_miss"] = (int(m[1]), int(m[2])) if m else (0, 0)
    m = re.search(r"WQ ROW_BUFFER_HIT:\s+(\d+)\s+ROW_BUFFER_MISS:\s+(\d+)\s+FULL:\s+(\d+)", t)
    d["wr_hit"], d["wr_miss"], d["wq_full"] = (int(m[1]), int(m[2]), int(m[3])) if m else (0, 0, 0)
    d["dbus_cong"] = rx(r"DBUS_CONGESTED:\s+(\d+)", t, int, 0)

    rd = [int(x[1]) for x in re.findall(r"^(\d+)banks busy for read cycles: (\d+)", t, re.M)]
    wr = [int(x[1]) for x in re.findall(r"^(\d+)banks busy for write cycles: (\d+)", t, re.M)]
    d["readmode_cycles"], d["writemode_cycles"] = sum(rd), sum(wr)
    d["ideal_writes"] = rx(r"DRAM ideal_writes=(\d)", t, int, None)

    m = re.search(r"enter_forced\(WQ>=high_wm\):\s+(\d+)\s+enter_idle\(RQ empty\):\s+(\d+)\s+exits:\s+(\d+)", t)
    if m:
        d["wm_forced"], d["wm_idle"], d["wm_exits"] = map(int, m.groups())
        m = re.search(r"write_mode_cycles_reads_waiting:\s+(\d+)\s+write_mode_cycles_RQ_empty:\s+(\d+)", t)
        d["wm_blocked"], d["wm_free"] = int(m[1]), int(m[2])
        m = re.search(r"reads_unscheduled_at_enter:\s+(\d+)\s+writes_unscheduled_at_exit:\s+(\d+)", t)
        d["rd_dropped"], d["wr_dropped"] = int(m[1]), int(m[2])
        m = re.search(r"reads_completed:\s+(\d+)\s+writes_completed:\s+(\d+)", t)
        d["rd_done"], d["wr_done"] = int(m[1]), int(m[2])
        m = re.search(r"writes_per_episode_hist\[[^\]]*\]:\s+((?:\d+\s*)+)", t)
        d["ep_hist"] = list(map(int, m[1].split())) if m else []
        m = re.search(r"read_rowmiss_cause closed/invalid:\s+(\d+)\s+bank_last_used_by_write:\s+(\d+)\s+read_read_conflict:\s+(\d+)", t)
        d["cause"] = list(map(int, m.groups())) if m else [0, 0, 0]
        m = re.search(r"RQ_depth_at_read_schedule_hist\[[^\]]*\]:\s+((?:\d+\s*)+)", t)
        d["depth"] = list(map(int, m[1].split())) if m else []
   
    ser = []
    for m in re.finditer(r"^WMSERIES (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)", t, re.M):
        i, cyc, nrd, nmiss, wait, nwr = map(int, m.groups())
        ser.append(dict(idx=i, cycle=cyc, reads=nrd, rowmiss=nmiss, blocked=wait, writes=nwr))
    d["series"] = ser
    return d


def policy_of(stem):
    for p in POLS:
        if stem.endswith("_" + p) or stem == p:
            return p, stem[: -len(p)].rstrip("_")
    return None, stem


def pct(a, b):
    return 100.0 * a / b if b else float("nan")


def fmt(v, kind):
    if v is None:
        return "-"
    if isinstance(v, float) and v != v:
        return "-"
    if kind == "i":
        return f"{int(v):,}"
    if kind == "p":
        return f"{v:.2f}"
    if kind == "f3":
        return f"{v:.3f}"
    if kind == "f4":
        return f"{v:.4f}"
    return str(v)


def print_table(labels, rows):
    w0 = max(len(r[0]) for r in rows) + 2
    cw = max(14, max(len(l) for l in labels) + 2)
    print("".ljust(w0) + "".join(l.rjust(cw) for l in labels))
    for name, vals in rows:
        if name.startswith("--"):
            print("\n" + name.strip("- "))
            continue
        print(name.ljust(w0) + "".join(v.rjust(cw) for v in vals))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--plot", help="save time-series figure (PNG)")
    ap.add_argument("--csv-dir", help="write per-run WMSERIES CSVs here")
    ap.add_argument("--compact", action="store_true")
    a = ap.parse_args()

    runs = []
    for f in a.files:
        d = parse(f)
        stem = os.path.splitext(os.path.basename(f))[0]
        d["stem"] = stem
        d["pol"], d["group"] = policy_of(stem)
        if d.get("incomplete"):
            print(f"WARNING: {f} has no final statistics (run not finished?) - skipped")
            continue
        runs.append(d)
    if not runs:
        sys.exit("no finished runs")
    runs.sort(key=lambda d: (d["group"], POLS.index(d["pol"]) if d["pol"] in POLS else 99, d["stem"]))
    base = {}
    for d in runs:
        if d["pol"] == "lru":
            base[d["group"]] = d
    prefix = os.path.commonprefix([d["stem"] for d in runs])
    prefix = prefix[: prefix.rfind("_") + 1] if "_" in prefix else ""
    for d in runs:
        d["label"] = d["stem"][len(prefix):] or d["stem"]
        b = base.get(d["group"])
        d["speedup"] = d["ipc"] / b["ipc"] if b else float("nan")
        tot = d["rd_hit"] + d["rd_miss"]
        d["rd_miss_pct"] = pct(d["rd_miss"], tot)
        d["wm_pct"] = pct(d["writemode_cycles"], d["cycles"])
        d["blocked_pct"] = pct(d["wm_blocked"], d["cycles"]) if "wm_blocked" in d else float("nan")

    ideal = {d["ideal_writes"] for d in runs if d["ideal_writes"] is not None}
    if ideal:
        print(f"[DRAM ideal_writes flag seen in logs: {sorted(ideal)}  (1 = writes free; ablation only)]")


    if a.compact or len(runs) > 6:
        print(f"{'run':<28}{'IPC':>9}{'spdup':>8}{'rdRowMiss%':>12}{'writeMode%':>12}{'blocked%':>10}")
        for d in runs:
            print(f"{d['label']:<28}{d['ipc']:>9.4f}{d['speedup']:>8.3f}{d['rd_miss_pct']:>12.2f}{d['wm_pct']:>12.2f}{fmt(d['blocked_pct'],'p'):>10}")
        print("\nSpread across runs of the SAME policy (noise check):")
        for p in POLS:
            xs = [d for d in runs if d["pol"] == p]
            if len(xs) > 1:
                ipc = [x["ipc"] for x in xs]
                rm = [x["rd_miss_pct"] for x in xs]
                wm = [x["wm_pct"] for x in xs]
                print(f"  {p:<11} n={len(xs)}  IPC {min(ipc):.4f}-{max(ipc):.4f}  rowMiss% {min(rm):.2f}-{max(rm):.2f}  writeMode% {min(wm):.2f}-{max(wm):.2f}")
        return

    labels = [d["label"] for d in runs]
    R = []
    g = lambda key, kind: [fmt(d.get(key), kind) for d in runs]
    R.append(("-- Performance", []))
    R.append(("instructions", g("instr", "i")))
    R.append(("cycles", g("cycles", "i")))
    R.append(("IPC", g("ipc", "f4")))
    R.append(("speedup vs LRU (same group)", g("speedup", "f4")))
    R.append(("-- LLC", []))
    R.append(("demand MPKI", g("dem_mpki", "f3")))
    R.append(("avg LLC miss latency (cyc)", g("llc_miss_lat", "p")))
    R.append(("-- DRAM reads", []))
    R.append(("reads (row hit+miss)", [fmt(d["rd_hit"] + d["rd_miss"], "i") for d in runs]))
    R.append(("read row-miss %", g("rd_miss_pct", "p")))
    R.append(("DBUS_CONGESTED", g("dbus_cong", "i")))
    R.append(("-- DRAM writes / write mode", []))
    R.append(("writes (row hit+miss)", [fmt(d["wr_hit"] + d["wr_miss"], "i") for d in runs]))
    R.append(("WQ FULL events", g("wq_full", "i")))
    R.append(("cycles in write mode", g("writemode_cycles", "i")))
    R.append(("  as % of total cycles", g("wm_pct", "p")))
    has = all("wm_blocked" in d for d in runs)
    if has:
        R.append(("  of which reads WAITING (blocked)", g("wm_blocked", "i")))
        R.append(("    blocked as % of total cycles", g("blocked_pct", "p")))
        R.append(("  of which RQ empty (free time)", g("wm_free", "i")))
        R.append(("write-mode entries: queue full", g("wm_forced", "i")))
        R.append(("write-mode entries: idle (RQ empty)", g("wm_idle", "i")))
        R.append(("write-mode exits", g("wm_exits", "i")))
        R.append(("writes completed per exit (avg)", [fmt(d["wr_done"] / d["wm_exits"] if d["wm_exits"] else float("nan"), "p") for d in runs]))
        R.append(("in-flight reads discarded at entry", g("rd_dropped", "i")))
        R.append(("in-flight writes discarded at exit", g("wr_dropped", "i")))
        R.append(("-- Why reads missed the row buffer (% of read row-misses)", []))
        tot = lambda d: sum(d["cause"])
        R.append(("bank row closed/invalid (reset or first use)", [fmt(pct(d["cause"][0], tot(d)), "p") for d in runs]))
        R.append(("bank last used by a WRITE", [fmt(pct(d["cause"][1], tot(d)), "p") for d in runs]))
        R.append(("read-read conflict (different row)", [fmt(pct(d["cause"][2], tot(d)), "p") for d in runs]))
        R.append(("-- Read queue depth when a read is scheduled", []))
        def avg_depth(d):
            h = d["depth"]; n = sum(h)
            return sum(i * c for i, c in enumerate(h)) / n if n else float("nan")
        R.append(("average depth", [fmt(avg_depth(d), "p") for d in runs]))
        R.append(("% of schedules with depth <= 1", [fmt(pct(sum(d["depth"][:2]), sum(d["depth"])), "p") for d in runs]))
        R.append(("% of schedules with depth >= 8", [fmt(pct(sum(d["depth"][8:]), sum(d["depth"])), "p") for d in runs]))
    else:
        R.append(("(instrumentation counters not found)", ["-"] * len(runs)))

    if any(d["series"] for d in runs):
        R.append(("-- Row-miss % per 100K reads (time series)", []))
        def q(d, frac):
            xs = sorted(100 * s["rowmiss"] / s["reads"] for s in d["series"])
            return xs[min(len(xs) - 1, int(frac * len(xs)))] if xs else float("nan")
        R.append(("intervals", [fmt(len(d["series"]), "i") for d in runs]))
        R.append(("p10", [fmt(q(d, .10), "p") for d in runs]))
        R.append(("median", [fmt(q(d, .50), "p") for d in runs]))
        R.append(("p90", [fmt(q(d, .90), "p") for d in runs]))
        R.append(("max", [fmt(q(d, .999), "p") for d in runs]))

    print_table(labels, R)

   
    print("\nWhere did the cycle savings vs LRU come from? (indicative, not strict causality)")
    for d in runs:
        b = base.get(d["group"])
        if not b or d is b:
            continue
        gap = b["cycles"] - d["cycles"]
        line = f"  {d['label']:<14} cycles saved {gap:>14,}"
        if gap != 0:
            line += f" | read-mode {pct(b['readmode_cycles']-d['readmode_cycles'], gap):6.1f}%  write-mode {pct(b['writemode_cycles']-d['writemode_cycles'], gap):6.1f}%"
            if "wm_blocked" in d and "wm_blocked" in b:
                line += f" | write-mode with reads waiting {pct(b['wm_blocked']-d['wm_blocked'], gap):6.1f}%"
        print(line)
    for d in runs:
        if "rd_done" in d:
            tot = d["rd_hit"] + d["rd_miss"]
            if tot and abs(d["rd_done"] - tot) / tot > 0.01:
                print(f"WARNING {d['label']}: instrumented reads ({d['rd_done']:,}) differ from controller reads ({tot:,}) by >1%")

   
    if a.csv_dir:
        os.makedirs(a.csv_dir, exist_ok=True)
        for d in runs:
            if d["series"]:
                with open(os.path.join(a.csv_dir, d["stem"] + ".csv"), "w") as fo:
                    fo.write("idx,cycle,reads,rowmiss,rowmiss_pct,blocked_cycles,writes_done\n")
                    for s in d["series"]:
                        fo.write(f"{s['idx']},{s['cycle']},{s['reads']},{s['rowmiss']},{100*s['rowmiss']/s['reads']:.3f},{s['blocked']},{s['writes']}\n")
        print(f"\nCSV time series written to {a.csv_dir}/")
    if a.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not installed: pip install matplotlib")
            return
        fig, ax = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
        for d in runs:
            if not d["series"]:
                continue
            x = [s["idx"] * 0.1 for s in d["series"]]  # millions of DRAM reads
            ax[0].plot(x, [100 * s["rowmiss"] / s["reads"] for s in d["series"]], label=d["label"])
            ax[1].plot(x, [s["blocked"] / 1e3 for s in d["series"]], label=d["label"])
            ax[2].plot(x, [s["writes"] for s in d["series"]], label=d["label"])
        ax[0].set_ylabel("read row-miss %\n(per 100K reads)")
        ax[1].set_ylabel("write-mode cycles with\nreads waiting (K)")
        ax[2].set_ylabel("writes completed\n(per 100K reads)")
        ax[2].set_xlabel("DRAM reads completed (millions)")
        ax[0].legend()
        fig.tight_layout()
        fig.savefig(a.plot, dpi=140)
        print(f"plot saved: {a.plot}")


if __name__ == "__main__":
    main()
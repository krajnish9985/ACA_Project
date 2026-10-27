
import re
import argparse
import os


CACHE_LEVELS = ["L1I", "L1D", "L2C", "LLC"]


def search_stats(pattern, text):
    """Return matched integer statistics, or None if absent."""
    m = re.search(pattern, text, re.MULTILINE)
    return tuple(map(int, m.groups())) if m else None


def safe_div(a, b):
    return a / b if b else 0.0


def parse(path, fclk):
    with open(path, "r", errors="replace") as f:
        text = f.read()

    m = re.search(
        r"CPU 0 cumulative IPC:\s*([\d.]+)\s+"
        r"instructions:\s*(\d+)\s+cycles:\s*(\d+)",
        text,
    )
    if not m:
        raise ValueError(f"Could not parse CPU statistics from {path}")

    ipc, instr, cycles = float(m[1]), int(m[2]), int(m[3])

    result = {
        "ipc": ipc,
        "instr": instr,
        "cycles": cycles,
        "caches": {},
    }

    
    for level in CACHE_LEVELS:
        total = search_stats(
            rf"{level}\s+TOTAL\s+ACCESS:\s*(\d+)\s+"
            rf"HIT:\s*(\d+)\s+MISS:\s*(\d+)",
            text,
        )

        if total is None:
            raise ValueError(
                f"Missing {level} TOTAL statistics in {path}"
            )

        access, hit, miss = total

        
        load = search_stats(
            rf"{level}\s+LOAD\s+ACCESS:\s*(\d+)\s+"
            rf"HIT:\s*(\d+)\s+MISS:\s*(\d+)",
            text,
        )

        rfo = search_stats(
            rf"{level}\s+RFO\s+ACCESS:\s*(\d+)\s+"
            rf"HIT:\s*(\d+)\s+MISS:\s*(\d+)",
            text,
        )

        lat_match = re.search(
            rf"{level}\s+AVERAGE MISS LATENCY:\s*([\d.]+)",
            text,
        )
        latency = float(lat_match[1]) if lat_match else None

        result["caches"][level] = {
            "access": access,
            "hit": hit,
            "miss": miss,
            "hit_rate": safe_div(hit, access) * 100,
            "miss_rate": safe_div(miss, access) * 100,
            "mpki": safe_div(miss, instr) * 1000,
            "load_access": load[0] if load else None,
            "load_hit": load[1] if load else None,
            "load_miss": load[2] if load else None,
            "load_mpki": (
                safe_div(load[2], instr) * 1000 if load else None
            ),
            "rfo_access": rfo[0] if rfo else None,
            "rfo_hit": rfo[1] if rfo else None,
            "rfo_miss": rfo[2] if rfo else None,
            "rfo_mpki": (
                safe_div(rfo[2], instr) * 1000 if rfo else None
            ),
            "miss_lat": latency,
        }

    
    llc = result["caches"]["LLC"]
    demand_misses = (
        (llc["load_miss"] or 0) + (llc["rfo_miss"] or 0)
    )
    result["dem_miss"] = demand_misses
    result["dem_mpki"] = safe_div(demand_misses, instr) * 1000

    
    rb = search_stats(
        r"RQ\s+ROW_BUFFER_HIT:\s*(\d+)\s+ROW_BUFFER_MISS:\s*(\d+)",
        text,
    )
    result["rowbuf_hit"] = (
        safe_div(rb[0], rb[0] + rb[1]) * 100
        if rb else None
    )

    
    result["dram_GBps"] = (
        llc["miss"] * 64 / (cycles / fclk) / 1e9
        if cycles else 0.0
    )

    return result


def fmt(value, spec=".3f"):
    return "-" if value is None else format(value, spec)


ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument(
    "--tokens",
    type=float,
    default=None,
    help="Tokens covered by the simulation window",
)
ap.add_argument("--fclk", type=float, default=4e9)
a = ap.parse_args()

rows = {
    os.path.splitext(os.path.basename(f))[0]: parse(f, a.fclk)
    for f in a.files
}


base_name = next(iter(rows))
base = rows[base_name]

print("\n=== CPU / SYSTEM METRICS ===")
print(
    f"{'Policy':<14}{'IPC':>9}{'Speedup':>10}"
    f"{'LLC dMPKI':>12}{'MissRed%':>11}"
    f"{'DRAM GB/s':>12}{'RBhit%':>10}"
    f"{'Cyc/tok':>13}{'Tok/s':>11}"
)

for name, r in rows.items():
    miss_reduction = (
        (base["dem_miss"] - r["dem_miss"])
        / base["dem_miss"] * 100
        if base["dem_miss"] else 0.0
    )

    cpt = safe_div(r["cycles"], a.tokens) if a.tokens else None
    tok_s = safe_div(a.fclk, cpt) if cpt else None

    print(
        f"{name:<14}{r['ipc']:>9.4f}"
        f"{safe_div(r['ipc'], base['ipc']):>10.4f}"
        f"{r['dem_mpki']:>12.3f}"
        f"{miss_reduction:>11.3f}"
        f"{r['dram_GBps']:>12.2f}"
        f"{fmt(r['rowbuf_hit']):>10}"
        f"{fmt(cpt, '.3e'):>13}"
        f"{fmt(tok_s):>11}"
    )

print("\n=== PER-CACHE-LEVEL METRICS ===")
print(
    f"{'Policy':<12}{'Cache':<7}{'Access':>12}"
    f"{'Hit':>12}{'Miss':>12}"
    f"{'Hit%':>9}{'Miss%':>9}{'MPKI':>10}"
    f"{'Load MPKI':>12}{'RFO MPKI':>11}{'MissLat':>11}"
)

for name, r in rows.items():
    for level in CACHE_LEVELS:
        c = r["caches"][level]
        print(
            f"{name:<12}{level:<7}"
            f"{c['access']:>12,d}"
            f"{c['hit']:>12,d}"
            f"{c['miss']:>12,d}"
            f"{c['hit_rate']:>9.3f}"
            f"{c['miss_rate']:>9.3f}"
            f"{c['mpki']:>10.3f}"
            f"{fmt(c['load_mpki']):>12}"
            f"{fmt(c['rfo_mpki']):>11}"
            f"{fmt(c['miss_lat']):>11}"
        )

print(f"\nBaseline policy: {base_name}")

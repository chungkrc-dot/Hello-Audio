"""
build_appendix_a_tables.py
--------------------------
Renders the Appendix A tables of docs/technical_manual.md from the batch CSV
produced by run_appendix_a.py.

The appendix carries three aggregates (overall, by instrument, per track) plus a
problem-track list and a low-yield floor, all derived from the same 41 rows.
Deriving them here rather than transcribing them by hand means the manual cannot
drift from the CSV it cites, and a re-run regenerates the prose figures — the
overall means, the per-instrument comparison and the engine-vs-engine verdict —
alongside the tables.

Aggregation is unweighted across tracks: each stem is one performance and counts
once, which is what the per-track tables below show. A note-weighted aggregate
would let the longest movements dominate the corpus figure.

Usage:
    python tests/scripts/batch/build_appendix_a_tables.py
"""
import os
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
RESULTS_CSV = PROJECT_ROOT / 'tests' / 'outputs' / 'batch_results' / 'appendix_a_results.csv'
OUT_MD = PROJECT_ROOT / 'tests' / 'outputs' / 'batch_results' / 'appendix_a_tables.md'

# REAPER detection yield below which a track is listed as a problem track.
PROBLEM_TRACK_THRESHOLD = 80.0

INSTRUMENT_ORDER = ["Cello", "Viola", "Violin"]


def overall_table(df):
    lines = ["| Engine | Detected Yield (%) | Included Yield (%) | Mean Deviation (Hz) |",
             "| :--- | :---: | :---: | :---: |"]
    for engine in ("REAPER", "pYIN"):
        lines.append(
            f"| **{engine}** | {df[f'Det_Yield_{engine}'].mean():.2f}% "
            f"| {df[f'Inc_Yield_{engine}'].mean():.2f}% "
            f"| {df[f'Dev_Hz_{engine}'].mean():+.2f} Hz |"
        )
    return lines


def instrument_table(df):
    lines = ["| Instrument | REAPER Det. (%) | REAPER Inc. (%) | REAPER Dev (Hz) "
             "| pYIN Det. (%) | pYIN Inc. (%) | pYIN Dev (Hz) |",
             "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |"]
    for inst in INSTRUMENT_ORDER:
        sub = df[df['Instrument'] == inst]
        if sub.empty:
            continue
        lines.append(
            f"| **{inst}** | {sub['Det_Yield_REAPER'].mean():.2f}% "
            f"| {sub['Inc_Yield_REAPER'].mean():.2f}% "
            f"| {sub['Dev_Hz_REAPER'].mean():+.2f} "
            f"| {sub['Det_Yield_pYIN'].mean():.2f}% "
            f"| {sub['Inc_Yield_pYIN'].mean():.2f}% "
            f"| {sub['Dev_Hz_pYIN'].mean():+.2f} |"
        )
    return lines


def per_track_table(df, engine):
    lines = ["| Dataset Piece | Part | Instrument | Det. Yield (%) | Inc. Yield (%) | Mean Dev. (Hz) |",
             "| :--- | :--- | :--- | :---: | :---: | :---: |"]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['Filename']} | {r['Piece']} | {r['Instrument']} "
            f"| {r[f'Det_Yield_{engine}']:.2f}% | {r[f'Inc_Yield_{engine}']:.2f}% "
            f"| {r[f'Dev_Hz_{engine}']:+.2f} |"
        )
    return lines


def problem_tracks(df):
    sub = df[df['Det_Yield_REAPER'] < PROBLEM_TRACK_THRESHOLD].sort_values('Filename')
    lines = [f"{len(sub)} tracks show REAPER detection yields below "
             f"{PROBLEM_TRACK_THRESHOLD:.0f}%.",
             "",
             "| Track | Inst. | REAPER Det | REAPER Inc | pYIN Det | pYIN Inc |",
             "| :--- | :--- | :---: | :---: | :---: | :---: |"]
    for _, r in sub.iterrows():
        lines.append(
            f"| {r['Filename']} | {r['Instrument']} | {r['Det_Yield_REAPER']:.2f}% "
            f"| {r['Inc_Yield_REAPER']:.2f}% | {r['Det_Yield_pYIN']:.2f}% "
            f"| {r['Inc_Yield_pYIN']:.2f}% |"
        )
    return lines


def engine_comparison(df):
    """
    Which engine leads on each instrument x metric cell.

    The appendix's headline claim is a statement about this table, so it is
    computed rather than asserted: the summary sentence is only as good as the
    cells it summarises, and those move whenever the corpus or the step pattern
    changes.
    """
    lines = ["| Instrument | Metric | REAPER | pYIN | Leader | Margin (pp) |",
             "| :--- | :--- | :---: | :---: | :---: | :---: |"]
    losses = []
    for inst in INSTRUMENT_ORDER:
        sub = df[df['Instrument'] == inst]
        if sub.empty:
            continue
        for metric, col in (("Detected", "Det_Yield"), ("Included", "Inc_Yield")):
            reaper = sub[f'{col}_REAPER'].mean()
            pyin = sub[f'{col}_pYIN'].mean()
            leader = "pYIN" if pyin > reaper else "REAPER"
            if leader != "pYIN":
                losses.append((inst, metric, reaper - pyin))
            lines.append(f"| {inst} | {metric} | {reaper:.2f}% | {pyin:.2f}% "
                         f"| **{leader}** | {abs(pyin - reaper):.2f} |")
    lines.append("")
    if losses:
        detail = "; ".join(f"{inst.lower()} {metric.lower()} yield, where REAPER leads by "
                           f"{margin:.2f} pp" for inst, metric, margin in losses)
        lines.append(f"**Verdict:** pYIN leads REAPER on every instrument class and metric "
                     f"except {detail}.")
    else:
        lines.append("**Verdict:** pYIN leads REAPER on every instrument class, on both "
                     "detected and included yield.")
    return lines


def low_yield_floors(df):
    lines = ["| Engine | Worst detected yield | Track |",
             "| :--- | :---: | :--- |"]
    for engine in ("pYIN", "REAPER"):
        row = df.loc[df[f'Det_Yield_{engine}'].idxmin()]
        lines.append(f"| {engine} | {row[f'Det_Yield_{engine}']:.2f}% | `{row['Filename']}` |")
    return lines


def main():
    if not RESULTS_CSV.exists():
        print(f"Error: {RESULTS_CSV} not found. Run run_appendix_a.py first.")
        sys.exit(1)

    df = pd.read_csv(RESULTS_CSV).sort_values('Filename').reset_index(drop=True)
    if df.empty:
        print("Error: results CSV has no rows.")
        sys.exit(1)

    counts = df['Instrument'].value_counts()
    out = [
        "# Appendix A tables (generated)",
        "",
        f"Source: `{RESULTS_CSV.relative_to(PROJECT_ROOT)}` — {len(df)} stems "
        + ", ".join(f"{counts.get(i, 0)} {i.lower()}" for i in INSTRUMENT_ORDER) + ".",
        "",
        "## 1. Overall Batch Performance",
        "",
        *overall_table(df),
        "",
        "## 2. Analysis by Instrument",
        "",
        *instrument_table(df),
        "",
        "## 2b. Engine comparison by cell",
        "",
        *engine_comparison(df),
        "",
        "## 3a. Problem tracks",
        "",
        *problem_tracks(df),
        "",
        "## 3b. Low-yield advisory floors",
        "",
        *low_yield_floors(df),
        "",
        "## 4. REAPER Engine Results",
        "",
        *per_track_table(df, "REAPER"),
        "",
        "## 5. pYIN Engine Results",
        "",
        *per_track_table(df, "pYIN"),
        "",
    ]

    OUT_MD.write_text("\n".join(out))
    print("\n".join(out))
    print(f"\n[+] Written to {OUT_MD}")


if __name__ == "__main__":
    main()

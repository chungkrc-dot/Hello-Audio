"""
Slope Filter & Switch Probability Ablation Study
================================================
Justifies the two non-default Engine Optimal Default parameters:

  - max_pitch_slope = 0.50 semitones/frame  (librosa/pYIN has no such filter)
  - switch_prob     = 0.005                 (librosa default is 0.01)

A full factorial grid of (max_pitch_slope x switch_prob) is swept over a
deterministic subset of URMP bowed-string tracks. For each cell the script
reports detection yield, inclusion yield, and the median/mean
|Deviation_Cents| of included notes, then identifies the parameter region
that maximises detection yield while holding median deviation low.

Because `switch_prob` is consumed inside `librosa.pyin()` but
`max_pitch_slope` is applied downstream in `analyze_intonation()` /
`process_dtw_alignment()`, the (expensive) pYIN extraction is performed once
per (track, switch_prob) and reused across all slope values.

Usage:
    python tests/scripts/validation/validate_slope_switchprob.py
"""

import os
import sys
import gc
import json
import numpy as np
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

import librosa

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded

REPORT_PATH = os.path.join(SCRIPT_DIR, 'slope_switchprob_report.md')
RESULTS_JSON = os.path.join(SCRIPT_DIR, 'slope_switchprob_results.json')

# librosa.pyin quantises f0 onto a grid of `resolution` semitones (default 0.1),
# so Deviation_Cents lands on multiples of 10 cents. Recorded here because it
# sets the floor on how finely the median can discriminate between grid cells.
PYIN_RESOLUTION_CENTS = 10.0

PYIN_PARAMS = {
    "rms_threshold": 0.005,
    "max_pitch_slope": 0.50,
    "min_frames": 2,
    "switch_prob": 0.005,
}

TOGGLES = {
    "freq_limits": True,
    "slope_filter": True,
    "duration_filter": True,
    "locked_target": True,
    "harmonic_folding": True,
    "force_global": True,
}

INST_MAP = {"vn": "Violin", "va": "Viola", "vc": "Cello"}

# --- Parameter grid ---
# 999.0 is a sentinel that keeps the slope filter enabled but sets the
# threshold above any physically realisable frame-to-frame pitch change,
# making it operationally equivalent to disabling the filter.
SLOPE_DISABLED = 999.0
SLOPE_GRID = [0.10, 0.25, 0.50, 0.75, 1.00, SLOPE_DISABLED]
SWITCH_PROB_GRID = [0.001, 0.005, 0.01, 0.02, 0.05]

# Deterministic subset: first N tracks per instrument (sorted by path).
TRACKS_PER_INSTRUMENT = 5

# Reference tuning for all analysis.
REFERENCE_PITCH_HZ = 440.0

# Tolerances defining the "optimal region" plateau.
YIELD_TOL = 1.0   # percentage points below the best detection yield
DEV_TOL = 0.5     # cents above the best mean |Deviation_Cents|


def slope_label(slope):
    return "disabled" if slope >= SLOPE_DISABLED else f"{slope:.2f}"


def extract(audio_path, instrument, switch_prob):
    """Runs the pYIN front-end once; the result is reused across slope values."""
    with open(audio_path, 'rb') as af:
        return extract_pitch_and_rms(
            af,
            instrument=instrument,
            switch_prob=switch_prob,
            enable_freq_limits=TOGGLES['freq_limits'],
            pitch_engine="pYIN"
        )


def run_downstream(y, sr, f0, voiced_flag, rms, midi_notes, max_pitch_slope):
    """Filters -> DTW alignment -> harmonic folding -> per-note metrics."""
    res = analyze_intonation(
        y, sr, f0, voiced_flag, rms,
        rms_threshold=PYIN_PARAMS['rms_threshold'],
        min_frames=PYIN_PARAMS['min_frames'],
        max_pitch_slope=max_pitch_slope,
        toggles=TOGGLES,
        reference_pitch_hz=REFERENCE_PITCH_HZ
    )
    final_mask = res['final_mask']

    time_array, expected, warped, _, folded_f0_hz, _, _, correction_array = process_dtw_alignment(
        midi_notes, f0, y, sr, final_mask, TOGGLES, max_pitch_slope
    )

    dtw_metrics = calculate_dtw_metrics(
        midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
    )

    del res, final_mask, time_array, expected, warped, folded_f0_hz, correction_array
    return dtw_metrics


def slope_rejection(f0, max_pitch_slope):
    """
    Fraction of voiced frame-to-frame transitions the slope filter rejects.

    Mirrors the slope computation in `generate_filters()` but reports it in
    isolation, so the filter's direct action is visible independently of the
    RMS, duration and DTW stages downstream.
    """
    midi = np.full_like(f0, np.nan)
    valid = ~np.isnan(f0)
    midi[valid] = librosa.hz_to_midi(f0[valid])
    slope = np.abs(np.diff(midi))
    finite = slope[~np.isnan(slope)]
    if finite.size == 0:
        return 0, 0
    return int(np.sum(finite > max_pitch_slope)), int(finite.size)


def discover_tracks(dataset_dir):
    audio_files = sorted(dataset_dir.rglob("AuSep_*.wav"))
    tracks = []

    for audio_path in audio_files:
        stem = audio_path.stem
        if stem.startswith('AuMix'):
            continue

        parts = stem.split('_')
        try:
            target_track = int(parts[1])
            inst_code = parts[2]
        except (IndexError, ValueError):
            continue

        instrument = INST_MAP.get(inst_code)
        if instrument is None:
            continue

        midi_files = list(audio_path.parent.glob("*.mid"))
        if not midi_files:
            print(f"  [!] No MIDI found for {stem}, skipping")
            continue

        tracks.append({
            'audio_path': str(audio_path),
            'midi_path': str(midi_files[0]),
            'stem': stem,
            'target_track': target_track,
            'instrument': instrument,
        })

    return tracks


def select_subset(tracks, per_instrument):
    """First `per_instrument` tracks of each instrument, in sorted path order."""
    subset = []
    for inst in ["Violin", "Viola", "Cello"]:
        inst_tracks = [t for t in tracks if t['instrument'] == inst]
        if not inst_tracks:
            print(f"  [!] No {inst} tracks available in dataset")
            continue
        if len(inst_tracks) < per_instrument:
            print(f"  [!] Only {len(inst_tracks)} {inst} tracks available "
                  f"(requested {per_instrument})")
        subset.extend(inst_tracks[:per_instrument])
    return subset


def load_midi_notes(midi_path, target_track):
    with open(midi_path, 'rb') as f:
        midi_notes = parse_midi_with_timing(f, target_track=target_track)
        if not midi_notes:
            f.seek(0)
            midi_notes = parse_midi_with_timing(f, target_track=0)
        if not midi_notes:
            f.seek(0)
            midi_notes = parse_midi_with_timing(f, target_track=1)
    return midi_notes


def main():
    print("=" * 60)
    print("Slope Filter & Switch Probability Ablation Study")
    print("Engine: pYIN | reference_pitch_hz=440.0")
    print(f"Grid: {len(SLOPE_GRID)} slopes x {len(SWITCH_PROB_GRID)} switch_probs "
          f"= {len(SLOPE_GRID) * len(SWITCH_PROB_GRID)} combinations")
    print("=" * 60)

    dataset_dir = Path(os.path.join(PROJECT_ROOT, 'dataset (Strings only)'))
    if not dataset_dir.exists():
        print(f"Error: Dataset not found at {dataset_dir}")
        sys.exit(1)

    all_tracks = discover_tracks(dataset_dir)
    tracks = select_subset(all_tracks, TRACKS_PER_INSTRUMENT)

    print(f"\n[INFO] Found {len(all_tracks)} string tracks; "
          f"using deterministic subset of {len(tracks)} "
          f"(first {TRACKS_PER_INSTRUMENT} per instrument).\n")

    if not tracks:
        print("No tracks found. Exiting.")
        sys.exit(1)

    # cells[(slope, switch_prob)] -> accumulators
    cells = {
        (s, sp): {'total_midi': 0, 'detected': 0, 'included': 0, 'abs_devs': [],
                  'slope_rejected': 0, 'slope_transitions': 0}
        for s in SLOPE_GRID for sp in SWITCH_PROB_GRID
    }

    n_processed = 0

    for i, t in enumerate(tracks, 1):
        stem = t['stem']
        instrument = t['instrument']
        print(f"[{i}/{len(tracks)}] {stem} ({instrument})", flush=True)

        midi_notes = load_midi_notes(t['midi_path'], t['target_track'])
        if not midi_notes:
            print(f"  [!] No MIDI notes found, skipping")
            continue

        total_midi = len(midi_notes)
        n_processed += 1

        for sp in SWITCH_PROB_GRID:
            try:
                y, sr, f0, voiced_flag, rms, _ = extract(t['audio_path'], instrument, sp)
            except Exception as e:
                print(f"  [!] Extraction failed at switch_prob={sp}: {e}")
                continue

            row = []
            for slope in SLOPE_GRID:
                metrics = run_downstream(y, sr, f0, voiced_flag, rms, midi_notes, slope)

                detected = 0
                included = 0
                abs_devs = []
                for m in metrics:
                    dev = m.get('Deviation_Cents', float('nan'))
                    if np.isnan(dev):
                        continue
                    detected += 1
                    if not is_note_excluded(m):
                        included += 1
                        abs_devs.append(abs(dev))

                n_rej, n_trans = slope_rejection(f0, slope)

                c = cells[(slope, sp)]
                c['total_midi'] += total_midi
                c['detected'] += detected
                c['included'] += included
                c['abs_devs'].extend(abs_devs)
                c['slope_rejected'] += n_rej
                c['slope_transitions'] += n_trans

                row.append(f"{slope_label(slope)}:{detected / total_midi * 100:.0f}%")
                del metrics

            print(f"  switch_prob={sp:<6} yields -> {'  '.join(row)}", flush=True)

            del y, sr, f0, voiced_flag, rms
            gc.collect()

    if n_processed == 0:
        print("\nNo tracks yielded MIDI notes. Exiting.")
        sys.exit(1)

    # --- Summarise cells ---
    results = {}
    for key, c in cells.items():
        devs = np.array(c['abs_devs'])
        results[key] = {
            'total_midi': c['total_midi'],
            'detected': c['detected'],
            'included': c['included'],
            'detection_yield': (c['detected'] / c['total_midi'] * 100) if c['total_midi'] else 0.0,
            'inclusion_yield': (c['included'] / c['detected'] * 100) if c['detected'] else 0.0,
            'median_dev': float(np.median(devs)) if devs.size else float('nan'),
            'mean_dev': float(np.mean(devs)) if devs.size else float('nan'),
            'p90_dev': float(np.percentile(devs, 90)) if devs.size else float('nan'),
            'n_dev': int(devs.size),
            'slope_reject_pct': (c['slope_rejected'] / c['slope_transitions'] * 100)
                                if c['slope_transitions'] else 0.0,
        }

    with open(RESULTS_JSON, 'w') as jf:
        json.dump(
            {'slope_grid': SLOPE_GRID, 'switch_prob_grid': SWITCH_PROB_GRID,
             'tracks': [t['stem'] for t in tracks],
             'cells': [{'max_pitch_slope': k[0], 'switch_prob': k[1], **v}
                       for k, v in results.items()]},
            jf, indent=2
        )

    print("\n" + "=" * 60)
    print("DETECTION YIELD (% of MIDI notes with non-NaN deviation)")
    print("=" * 60)
    print_matrix(results, 'detection_yield', "{:.1f}%")

    print("\n" + "=" * 60)
    print("INCLUSION YIELD (% of detected notes passing is_note_excluded)")
    print("=" * 60)
    print_matrix(results, 'inclusion_yield', "{:.1f}%")

    print("\n" + "=" * 60)
    print("MEDIAN |Deviation_Cents| (included notes)")
    print("=" * 60)
    print_matrix(results, 'median_dev', "{:.2f}")

    print("\n" + "=" * 60)
    print("MEAN |Deviation_Cents| (included notes)")
    print("=" * 60)
    print_matrix(results, 'mean_dev', "{:.2f}")

    print("\n" + "=" * 60)
    print("SLOPE FILTER REJECTION RATE (% of voiced frame transitions)")
    print("=" * 60)
    print_matrix(results, 'slope_reject_pct', "{:.2f}")

    n_distinct_medians = len({round(r['median_dev'], 6) for r in results.values()
                              if not np.isnan(r['median_dev'])})
    print(f"\n[!] Distinct median |dev| values across all {len(results)} cells: {n_distinct_medians}")
    print(f"    librosa.pyin quantises f0 to a {PYIN_RESOLUTION_CENTS:.0f}-cent grid, so the median")
    print(f"    is degenerate at this scale. Mean |dev| is used as the accuracy axis below.")

    frontier = pareto_frontier(results)
    optimal = identify_optimal(results)

    print("\n" + "-" * 50)
    print("PARETO FRONTIER (max detection yield / min mean |dev|)")
    print("-" * 50)
    for slope, sp in frontier:
        r = results[(slope, sp)]
        print(f"    slope={slope_label(slope):>8}  switch_prob={sp:<6} "
              f"det={r['detection_yield']:.1f}%  mean={r['mean_dev']:.2f}c")

    print("\n" + "-" * 50)
    print("OPTIMAL REGION")
    print("-" * 50)
    best_det = max(r['detection_yield'] for r in results.values())
    best_mean = min(r['mean_dev'] for r in results.values() if not np.isnan(r['mean_dev']))
    print(f"  Best detection yield anywhere in grid: {best_det:.1f}%")
    print(f"  Best mean |dev| anywhere in grid:      {best_mean:.2f} cents")
    print(f"  Cells within {YIELD_TOL} pp of best yield AND {DEV_TOL} c of best mean: {len(optimal)}")
    for slope, sp in optimal:
        r = results[(slope, sp)]
        marker = "  <-- Engine Optimal Default" if (
            slope == PYIN_PARAMS['max_pitch_slope'] and sp == PYIN_PARAMS['switch_prob']
        ) else ""
        print(f"    slope={slope_label(slope):>8}  switch_prob={sp:<6} "
              f"det={r['detection_yield']:.1f}%  mean={r['mean_dev']:.2f}c{marker}")

    print("\n" + "-" * 50)
    print("MARGINAL EFFECTS (range across the grid)")
    print("-" * 50)
    for name, grid, key_idx in [("max_pitch_slope", SLOPE_GRID, 0),
                                ("switch_prob", SWITCH_PROB_GRID, 1)]:
        dets, means = [], []
        for v in grid:
            sel = [r for k, r in results.items() if k[key_idx] == v]
            dets.append(np.mean([r['detection_yield'] for r in sel]))
            means.append(np.mean([r['mean_dev'] for r in sel]))
        print(f"  {name:<16} detection yield spans {max(dets) - min(dets):.2f} pp, "
              f"mean |dev| spans {max(means) - min(means):.2f} c")

    generate_report(results, optimal, frontier, tracks, n_processed)

    print(f"\n[+] Report saved to {REPORT_PATH}")
    print("=" * 60)


def print_matrix(results, field, fmt):
    header = "  slope \\ sp  " + "".join(f"{sp:>10}" for sp in SWITCH_PROB_GRID)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for slope in SLOPE_GRID:
        row = f"  {slope_label(slope):>11}  "
        for sp in SWITCH_PROB_GRID:
            v = results[(slope, sp)][field]
            row += f"{('—' if np.isnan(v) else fmt.format(v)):>10}"
        print(row)


def identify_optimal(results, yield_tol=None, dev_tol=None):
    """
    Cells whose detection yield is within `yield_tol` percentage points of the
    grid maximum AND whose mean |dev| is within `dev_tol` cents of the grid
    minimum — the flat plateau of the yield/accuracy trade-off.

    Mean rather than median is the accuracy axis: librosa.pyin quantises f0 onto
    a 10-cent grid, which makes the median identical across every cell and thus
    useless as a discriminator.
    """
    yield_tol = YIELD_TOL if yield_tol is None else yield_tol
    dev_tol = DEV_TOL if dev_tol is None else dev_tol
    valid = {k: r for k, r in results.items() if not np.isnan(r['mean_dev'])}
    if not valid:
        return []
    best_det = max(r['detection_yield'] for r in valid.values())
    best_mean = min(r['mean_dev'] for r in valid.values())
    return sorted(
        k for k, r in valid.items()
        if r['detection_yield'] >= best_det - yield_tol
        and r['mean_dev'] <= best_mean + dev_tol
    )


def pareto_frontier(results):
    """Cells not dominated on both detection yield (max) and mean |dev| (min)."""
    valid = {k: r for k, r in results.items() if not np.isnan(r['mean_dev'])}
    front = []
    for k, r in valid.items():
        dominated = any(
            o['detection_yield'] >= r['detection_yield']
            and o['mean_dev'] <= r['mean_dev']
            and (o['detection_yield'] > r['detection_yield'] or o['mean_dev'] < r['mean_dev'])
            for o in valid.values()
        )
        if not dominated:
            front.append(k)
    return sorted(front)


def matrix_table(results, field, fmt):
    lines = []
    lines.append("| `max_pitch_slope` | " + " | ".join(f"$\\beta = {sp}$" for sp in SWITCH_PROB_GRID) + " |")
    lines.append("| :---: |" + " :---: |" * len(SWITCH_PROB_GRID))
    for slope in SLOPE_GRID:
        cells = []
        for sp in SWITCH_PROB_GRID:
            v = results[(slope, sp)][field]
            cells.append("—" if np.isnan(v) else fmt.format(v))
        label = slope_label(slope)
        label = "disabled" if label == "disabled" else f"`{label}`"
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def generate_report(results, optimal, frontier, tracks, n_processed):
    lines = []
    lines.append("# Slope Filter & Switch Probability Ablation Study")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # --- Methodology ---
    lines.append("## Methodology")
    lines.append("")
    lines.append("The pYIN engine was run through the full production pipeline "
                 "(extract → intonation filters → DTW alignment → harmonic folding → metrics) "
                 f"over a full factorial grid of {len(SLOPE_GRID)} `max_pitch_slope` values × "
                 f"{len(SWITCH_PROB_GRID)} `switch_prob` values "
                 f"({len(SLOPE_GRID) * len(SWITCH_PROB_GRID)} combinations). All other "
                 "parameters were held at Engine Optimal Defaults "
                 f"(`rms_threshold=0.005`, `min_frames=2`, `reference_pitch_hz={REFERENCE_PITCH_HZ}`).")
    lines.append("")
    lines.append("Because `switch_prob` is consumed inside `librosa.pyin()` while `max_pitch_slope` "
                 "is applied downstream, the pitch extraction was performed once per "
                 "(track, `switch_prob`) pair and reused across all slope values — the grid is "
                 "therefore exact, not approximated.")
    lines.append("")
    lines.append(f"**Track subset.** To keep runtime tractable the sweep used a deterministic "
                 f"subset: the first {TRACKS_PER_INSTRUMENT} tracks of each instrument in sorted "
                 f"path order ({len(tracks)} selected, {n_processed} yielding parsable MIDI). "
                 "Selection is fixed rather than random so the study is reproducible.")
    lines.append("")
    lines.append("**Metrics per cell:**")
    lines.append("")
    lines.append("- **Detection yield** — % of MIDI reference notes receiving a non-NaN `Deviation_Cents`.")
    lines.append("- **Inclusion yield** — % of *detected* notes surviving `is_note_excluded()` "
                 "($|\\text{dev}| \\le 100$ c and no harmonic-folding correction).")
    lines.append("- **Median / Mean / P90 $|\\text{Deviation\\_Cents}|$** — over included notes only.")
    lines.append("- **Slope filter rejection rate** — % of voiced frame-to-frame transitions whose "
                 "$|\\Delta p_{midi}|$ exceeds `max_pitch_slope`, measured in isolation from the "
                 "RMS, duration and DTW stages.")
    lines.append("")
    lines.append("`max_pitch_slope = 999.0` is a sentinel above any physically realisable "
                 "frame-to-frame pitch change; it is operationally equivalent to disabling the "
                 "slope filter and is reported as **disabled**.")
    lines.append("")

    # --- Tracks ---
    lines.append("## Track Subset")
    lines.append("")
    lines.append("| # | Track | Instrument |")
    lines.append("| :---: | :--- | :---: |")
    for i, t in enumerate(tracks, 1):
        lines.append(f"| {i} | {t['stem']} | {t['instrument']} |")
    lines.append("")

    # --- Matrices ---
    lines.append("## Detection Yield (%)")
    lines.append("")
    lines.extend(matrix_table(results, 'detection_yield', "{:.1f}"))

    lines.append("## Inclusion Yield (% of detected)")
    lines.append("")
    lines.extend(matrix_table(results, 'inclusion_yield', "{:.1f}"))

    lines.append("## Median $|\\text{Deviation\\_Cents}|$ (included notes)")
    lines.append("")
    lines.extend(matrix_table(results, 'median_dev', "{:.2f}"))

    n_distinct = len({round(r['median_dev'], 6) for r in results.values()
                      if not np.isnan(r['median_dev'])})
    lines.append("> [!IMPORTANT]")
    lines.append(f"> The median takes only **{n_distinct}** distinct value(s) across all "
                 f"{len(results)} grid cells. `librosa.pyin()` quantises $f_0$ onto a grid of "
                 f"`resolution = 0.1` semitones, so every `Deviation_Cents` value is a multiple "
                 f"of {PYIN_RESOLUTION_CENTS:.0f} cents and the median collapses onto that grid. "
                 "The median is therefore **not** a usable discriminator at this scale; "
                 "**mean $|\\text{dev}|$ is used as the accuracy axis** for identifying the "
                 "optimal region.")
    lines.append("")

    lines.append("## Mean $|\\text{Deviation\\_Cents}|$ (included notes)")
    lines.append("")
    lines.extend(matrix_table(results, 'mean_dev', "{:.2f}"))

    lines.append("## 90th Percentile $|\\text{Deviation\\_Cents}|$ (included notes)")
    lines.append("")
    lines.extend(matrix_table(results, 'p90_dev', "{:.2f}"))

    lines.append("## Slope Filter Rejection Rate (% of voiced frame transitions)")
    lines.append("")
    lines.extend(matrix_table(results, 'slope_reject_pct', "{:.2f}"))

    lines.append("## Included Note Counts")
    lines.append("")
    lines.extend(matrix_table(results, 'included', "{:.0f}"))

    # --- Marginal effects ---
    lines.append("## Marginal Effects")
    lines.append("")
    lines.append("Each parameter's total influence, averaged over all levels of the other:")
    lines.append("")
    lines.append("| Parameter | Detection yield range | Mean \\|dev\\| range |")
    lines.append("| :--- | :---: | :---: |")
    for name, grid, key_idx in [("`max_pitch_slope`", SLOPE_GRID, 0),
                                ("`switch_prob`", SWITCH_PROB_GRID, 1)]:
        dets, means = [], []
        for v in grid:
            sel = [r for k, r in results.items() if k[key_idx] == v]
            dets.append(np.mean([r['detection_yield'] for r in sel]))
            means.append(np.mean([r['mean_dev'] for r in sel]))
        lines.append(f"| {name} | {max(dets) - min(dets):.2f} pp | {max(means) - min(means):.2f} c |")
    lines.append("")

    # --- Pareto frontier ---
    lines.append("## Pareto Frontier")
    lines.append("")
    lines.append("Cells not dominated on both axes (higher detection yield **and** lower "
                 "mean $|\\text{dev}|$):")
    lines.append("")
    lines.append("| `max_pitch_slope` | `switch_prob` | Detection Yield | Mean \\|dev\\| (c) |")
    lines.append("| :---: | :---: | :---: | :---: |")
    for slope, sp in frontier:
        r = results[(slope, sp)]
        lines.append(f"| {slope_label(slope)} | {sp} | {r['detection_yield']:.1f}% "
                     f"| {r['mean_dev']:.2f} |")
    lines.append("")

    # --- Optimal region ---
    lines.append("## Optimal Region")
    lines.append("")
    valid = {k: r for k, r in results.items() if not np.isnan(r['mean_dev'])}
    if valid:
        best_det = max(r['detection_yield'] for r in valid.values())
        best_mean = min(r['mean_dev'] for r in valid.values())
        lines.append(f"- **Maximum detection yield in grid**: {best_det:.1f}%")
        lines.append(f"- **Minimum mean $|\\text{{dev}}|$ in grid**: {best_mean:.2f} cents")
        lines.append("")
        lines.append(f"The optimal region is defined as those cells simultaneously within "
                     f"{YIELD_TOL} percentage point of the maximum detection yield **and** within "
                     f"{DEV_TOL} cent of the minimum mean deviation — the flat plateau of the "
                     f"yield/accuracy trade-off.")
        lines.append("")
        lines.append("| `max_pitch_slope` | `switch_prob` | Detection Yield | Inclusion Yield | Mean \\|dev\\| (c) | Slope Reject % |")
        lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
        for slope, sp in optimal:
            r = results[(slope, sp)]
            note = " **(Engine Optimal Default)**" if (
                slope == PYIN_PARAMS['max_pitch_slope'] and sp == PYIN_PARAMS['switch_prob']
            ) else ""
            lines.append(f"| {slope_label(slope)}{note} | {sp} | {r['detection_yield']:.1f}% "
                         f"| {r['inclusion_yield']:.1f}% | {r['mean_dev']:.2f} | {r['slope_reject_pct']:.2f}% |")
        lines.append("")

        default_key = (PYIN_PARAMS['max_pitch_slope'], PYIN_PARAMS['switch_prob'])
        librosa_key = (PYIN_PARAMS['max_pitch_slope'], 0.01)
        d = results.get(default_key)
        if d:
            lines.append("### Production Setting vs. Grid")
            lines.append("")
            lines.append(f"The production configuration (`max_pitch_slope=0.50`, `switch_prob=0.005`) "
                         f"achieves {d['detection_yield']:.1f}% detection yield, "
                         f"{d['inclusion_yield']:.1f}% inclusion yield, and a mean "
                         f"$|\\text{{dev}}|$ of {d['mean_dev']:.2f} cents "
                         f"({d['included']} included notes) — "
                         f"{'inside' if default_key in optimal else 'outside'} the optimal region.")
            lines.append("")
            lb = results.get(librosa_key)
            if lb:
                lines.append(f"Against the librosa default `switch_prob=0.01` at the same slope: "
                             f"detection yield {lb['detection_yield']:.1f}% "
                             f"($\\Delta = {d['detection_yield'] - lb['detection_yield']:+.1f}$ pp), "
                             f"mean $|\\text{{dev}}|$ {lb['mean_dev']:.2f} cents "
                             f"($\\Delta = {d['mean_dev'] - lb['mean_dev']:+.2f}$ c).")
                lines.append("")
            dis = results.get((SLOPE_DISABLED, PYIN_PARAMS['switch_prob']))
            if dis:
                lines.append(f"Against a disabled slope filter at the same `switch_prob`: "
                             f"detection yield {dis['detection_yield']:.1f}% "
                             f"($\\Delta = {d['detection_yield'] - dis['detection_yield']:+.1f}$ pp), "
                             f"mean $|\\text{{dev}}|$ {dis['mean_dev']:.2f} cents "
                             f"($\\Delta = {d['mean_dev'] - dis['mean_dev']:+.2f}$ c), "
                             f"inclusion yield {dis['inclusion_yield']:.1f}% "
                             f"($\\Delta = {d['inclusion_yield'] - dis['inclusion_yield']:+.1f}$ pp).")
                lines.append("")
    else:
        lines.append("No cell produced any included notes.")
        lines.append("")

    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    main()

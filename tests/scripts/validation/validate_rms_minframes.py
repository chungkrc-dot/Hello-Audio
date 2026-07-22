"""
RMS Threshold & Minimum Duration Ablation Study
==============================================
Completes the comprehensive parameter sensitivity analysis by sweeping the
two Engine Optimal Defaults not covered by the confidence-threshold study
(task #2) or the slope/switch_prob ablation (task #5):

  - rms_threshold = 0.005   (amplitude gate on voiced frames)
  - min_frames    = 2       (minimum note-island duration, pYIN)

A full factorial grid of (rms_threshold x min_frames) is swept over every
bowed-string track in the URMP corpus — the same set used by
`validate_slope_switchprob.py`, so the two studies are directly comparable —
and each cell is reported both pooled and as a per-track mean with a 95%
confidence interval.

`rms_threshold` is swept as a nominal value but instrumented as an *effective*
one: `analyze_intonation()` silently raises it to max(rms_threshold,
2 x P10(RMS)), so on tracks where the adaptive floor dominates the swept value
does nothing at all. The binding rate and the mean effective threshold are
reported per cell for exactly this reason.

Both parameters are consumed *downstream* of `librosa.pyin()`, inside
`analyze_intonation()`. The expensive pYIN extraction is therefore performed
exactly once per track and reused across the entire grid — unlike the
slope/switch_prob study, where `switch_prob` is consumed inside pyin itself
and forced one extraction per (track, switch_prob) pair.

Usage:
    python tests/scripts/validation/validate_rms_minframes.py
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

from src.pitch_engine import (
    extract_pitch_and_rms, analyze_intonation, generate_filters, apply_duration_filter
)
from src.midi_parser import load_part_notes, MidiTrackError
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded

REPORT_PATH = os.path.join(SCRIPT_DIR, 'rms_minframes_report.md')
RESULTS_JSON = os.path.join(SCRIPT_DIR, 'rms_minframes_results.json')

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
RMS_GRID = [0.001, 0.0025, 0.005, 0.01, 0.02, 0.05]
MIN_FRAMES_GRID = [1, 2, 4, 8, 16]

# Reference tuning for all analysis.
REFERENCE_PITCH_HZ = 440.0

# Tolerances defining the "optimal region" plateau.
YIELD_TOL = 1.0   # percentage points below the best detection yield
DEV_TOL = 0.5     # cents above the best mean |Deviation_Cents|


def extract(audio_path, instrument):
    """Runs the pYIN front-end once; the result is reused across the whole grid."""
    with open(audio_path, 'rb') as af:
        return extract_pitch_and_rms(
            af,
            instrument=instrument,
            switch_prob=PYIN_PARAMS['switch_prob'],
            enable_freq_limits=TOGGLES['freq_limits'],
            pitch_engine="pYIN"
        )


def run_downstream(y, sr, f0, voiced_flag, rms, midi_notes, rms_threshold, min_frames):
    """Filters -> DTW alignment -> harmonic folding -> per-note metrics."""
    res = analyze_intonation(
        y, sr, f0, voiced_flag, rms,
        rms_threshold=rms_threshold,
        min_frames=min_frames,
        max_pitch_slope=PYIN_PARAMS['max_pitch_slope'],
        toggles=TOGGLES,
        reference_pitch_hz=REFERENCE_PITCH_HZ
    )
    final_mask = res['final_mask']

    time_array, expected, warped, _, folded_f0_hz, _, _, correction_array = process_dtw_alignment(
        midi_notes, f0, y, sr, final_mask, TOGGLES, PYIN_PARAMS['max_pitch_slope']
    )

    dtw_metrics = calculate_dtw_metrics(
        midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
    )

    del res, final_mask, time_array, expected, warped, folded_f0_hz, correction_array
    return dtw_metrics


def effective_rms_threshold(rms, rms_threshold):
    """
    Reproduces the adaptive noise-floor rule inside `analyze_intonation()`:

        effective = max(rms_threshold, percentile(rms, 10) * 2.0)

    The nominal parameter is only *binding* when it exceeds twice the track's
    10th-percentile RMS. Below that the adaptive floor takes over and the swept
    value has no effect whatsoever — this must be measured, not assumed.
    """
    if len(rms) == 0:
        return rms_threshold, False
    floor = float(np.percentile(rms, 10)) * 2.0
    return max(rms_threshold, floor), rms_threshold >= floor


def filter_action(f0, voiced_flag, rms, rms_threshold, min_frames):
    """
    Direct action of the two filters under test, measured in isolation from the
    DTW stage downstream.

      - RMS gate rate: % of voiced frames whose RMS falls at or below the
        *effective* threshold, i.e. frames the amplitude gate removes.
      - Duration destruction rate: % of candidate note-islands (contiguous runs
        in the combined mask) shorter than `min_frames`, i.e. islands the
        duration filter destroys outright.

    Mirrors `generate_filters()` / `apply_duration_filter()` rather than
    re-deriving them, so the numbers describe the production code path.
    """
    eff, binding = effective_rms_threshold(rms, rms_threshold)

    n_voiced = int(np.sum(voiced_flag))
    n_gated = int(np.sum(voiced_flag & (rms <= eff)))

    combined = generate_filters(
        f0, voiced_flag, rms, eff, PYIN_PARAMS['max_pitch_slope'],
        enable_slope_filter=TOGGLES['slope_filter']
    )

    padded = np.concatenate(([False], combined, [False]))
    changes = np.diff(padded.astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    durations = ends - starts

    n_islands = int(durations.size)
    n_destroyed = int(np.sum(durations < min_frames))
    n_frames_lost = int(np.sum(durations[durations < min_frames]))
    n_frames_candidate = int(np.sum(durations))

    del combined, padded, changes
    return {
        'voiced_frames': n_voiced,
        'rms_gated_frames': n_gated,
        'islands': n_islands,
        'islands_destroyed': n_destroyed,
        'island_frames': n_frames_candidate,
        'island_frames_lost': n_frames_lost,
        'effective_threshold': eff,
        'binding': binding,
    }


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


def instrument_counts(tracks):
    counts = {}
    for t in tracks:
        counts[t['instrument']] = counts.get(t['instrument'], 0) + 1
    return counts


def load_midi_notes(midi_path, target_track):
    """Strictly resolve one part; raises MidiTrackError rather than guessing."""
    midi_notes, _ = load_part_notes(midi_path, part_index=target_track)
    return midi_notes


# z for a two-sided 95% interval.
Z_95 = 1.96


def mean_ci(values):
    """
    Mean of a per-track statistic with a 95% normal-approximation CI on the mean.

    The unit of replication is the track, not the note: notes within a track are
    not independent draws, so a note-level interval would be far too narrow.
    """
    arr = np.asarray([v for v in values if not np.isnan(v)], dtype=float)
    n = arr.size
    if n == 0:
        return float('nan'), float('nan'), float('nan'), 0
    mean = float(np.mean(arr))
    if n < 2:
        return mean, mean, mean, n
    half = Z_95 * float(np.std(arr, ddof=1)) / np.sqrt(n)
    return mean, mean - half, mean + half, n


def main():
    print("=" * 60)
    print("RMS Threshold & Minimum Duration Ablation Study")
    print("Engine: pYIN | reference_pitch_hz=440.0")
    print(f"Grid: {len(RMS_GRID)} rms_thresholds x {len(MIN_FRAMES_GRID)} min_frames "
          f"= {len(RMS_GRID) * len(MIN_FRAMES_GRID)} combinations")
    print("Extraction: once per track (both parameters are downstream of pyin)")
    print("=" * 60)

    dataset_dir = Path(os.path.join(PROJECT_ROOT, 'dataset (Strings only)'))
    if not dataset_dir.exists():
        print(f"Error: Dataset not found at {dataset_dir}")
        sys.exit(1)

    tracks = discover_tracks(dataset_dir)

    counts = instrument_counts(tracks)
    print(f"\n[INFO] Sweeping the full corpus: {len(tracks)} string tracks "
          f"({', '.join(f'{n} {inst.lower()}' for inst, n in sorted(counts.items()))}).\n")

    if not tracks:
        print("No tracks found. Exiting.")
        sys.exit(1)

    # cells[(rms_threshold, min_frames)] -> accumulators. `track_det_yields` /
    # `track_mean_devs` hold one value per track so the corpus-level figures can
    # carry a confidence interval rather than standing as bare point estimates.
    cells = {
        (r, mf): {'total_midi': 0, 'detected': 0, 'included': 0, 'abs_devs': [],
                  'voiced_frames': 0, 'rms_gated_frames': 0,
                  'islands': 0, 'islands_destroyed': 0,
                  'island_frames': 0, 'island_frames_lost': 0,
                  'binding_tracks': 0, 'n_tracks': 0, 'eff_thresholds': [],
                  'track_det_yields': [], 'track_mean_devs': []}
        for r in RMS_GRID for mf in MIN_FRAMES_GRID
    }

    n_processed = 0

    for i, t in enumerate(tracks, 1):
        stem = t['stem']
        instrument = t['instrument']
        print(f"[{i}/{len(tracks)}] {stem} ({instrument})", flush=True)

        try:
            midi_notes = load_midi_notes(t['midi_path'], t['target_track'])
        except MidiTrackError as exc:
            print(f"  [!] {exc}")
            continue
        if not midi_notes:
            print(f"  [!] No MIDI notes found, skipping")
            continue

        try:
            y, sr, f0, voiced_flag, rms, _ = extract(t['audio_path'], instrument)
        except Exception as e:
            print(f"  [!] Extraction failed: {e}")
            continue

        total_midi = len(midi_notes)
        n_processed += 1

        noise_floor2 = float(np.percentile(rms, 10)) * 2.0 if len(rms) else 0.0
        print(f"  adaptive noise floor (2 x P10 RMS) = {noise_floor2:.5f}", flush=True)

        for r in RMS_GRID:
            row = []
            for mf in MIN_FRAMES_GRID:
                metrics = run_downstream(y, sr, f0, voiced_flag, rms, midi_notes, r, mf)

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

                fa = filter_action(f0, voiced_flag, rms, r, mf)

                c = cells[(r, mf)]
                c['total_midi'] += total_midi
                c['detected'] += detected
                c['included'] += included
                c['abs_devs'].extend(abs_devs)
                c['voiced_frames'] += fa['voiced_frames']
                c['rms_gated_frames'] += fa['rms_gated_frames']
                c['islands'] += fa['islands']
                c['islands_destroyed'] += fa['islands_destroyed']
                c['island_frames'] += fa['island_frames']
                c['island_frames_lost'] += fa['island_frames_lost']
                c['binding_tracks'] += int(fa['binding'])
                c['n_tracks'] += 1
                c['eff_thresholds'].append(fa['effective_threshold'])
                c['track_det_yields'].append(detected / total_midi * 100)
                c['track_mean_devs'].append(float(np.mean(abs_devs)) if abs_devs
                                            else float('nan'))

                row.append(f"mf={mf}:{detected / total_midi * 100:.0f}%")
                del metrics

            print(f"  rms_threshold={r:<7} yields -> {'  '.join(row)}", flush=True)

        del y, sr, f0, voiced_flag, rms
        gc.collect()

    if n_processed == 0:
        print("\nNo tracks yielded MIDI notes. Exiting.")
        sys.exit(1)

    # --- Summarise cells ---
    results = {}
    for key, c in cells.items():
        devs = np.array(c['abs_devs'])
        det_mean, det_lo, det_hi, n_tracks = mean_ci(c['track_det_yields'])
        dev_mean, dev_lo, dev_hi, _ = mean_ci(c['track_mean_devs'])
        results[key] = {
            'n_tracks_ci': n_tracks,
            'track_det_yield_mean': det_mean,
            'track_det_yield_ci_lo': det_lo,
            'track_det_yield_ci_hi': det_hi,
            'track_mean_dev_mean': dev_mean,
            'track_mean_dev_ci_lo': dev_lo,
            'track_mean_dev_ci_hi': dev_hi,
            'total_midi': c['total_midi'],
            'detected': c['detected'],
            'included': c['included'],
            'detection_yield': (c['detected'] / c['total_midi'] * 100) if c['total_midi'] else 0.0,
            'inclusion_yield': (c['included'] / c['detected'] * 100) if c['detected'] else 0.0,
            'median_dev': float(np.median(devs)) if devs.size else float('nan'),
            'mean_dev': float(np.mean(devs)) if devs.size else float('nan'),
            'p90_dev': float(np.percentile(devs, 90)) if devs.size else float('nan'),
            'n_dev': int(devs.size),
            'rms_gate_pct': (c['rms_gated_frames'] / c['voiced_frames'] * 100)
                            if c['voiced_frames'] else 0.0,
            'island_destroy_pct': (c['islands_destroyed'] / c['islands'] * 100)
                                  if c['islands'] else 0.0,
            'island_frame_loss_pct': (c['island_frames_lost'] / c['island_frames'] * 100)
                                     if c['island_frames'] else 0.0,
            'binding_pct': (c['binding_tracks'] / c['n_tracks'] * 100) if c['n_tracks'] else 0.0,
            'mean_effective_threshold': float(np.mean(c['eff_thresholds']))
                                        if c['eff_thresholds'] else float('nan'),
            'min_effective_threshold': float(np.min(c['eff_thresholds']))
                                       if c['eff_thresholds'] else float('nan'),
            'max_effective_threshold': float(np.max(c['eff_thresholds']))
                                       if c['eff_thresholds'] else float('nan'),
        }

    with open(RESULTS_JSON, 'w') as jf:
        json.dump(
            {'rms_grid': RMS_GRID, 'min_frames_grid': MIN_FRAMES_GRID,
             'tracks': [t['stem'] for t in tracks],
             'cells': [{'rms_threshold': k[0], 'min_frames': k[1], **v}
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
    print("RMS GATE RATE (% of voiced frames removed by amplitude gate)")
    print("=" * 60)
    print_matrix(results, 'rms_gate_pct', "{:.2f}")

    print("\n" + "=" * 60)
    print("DURATION FILTER (% of candidate islands destroyed)")
    print("=" * 60)
    print_matrix(results, 'island_destroy_pct', "{:.2f}")

    print("\n" + "=" * 60)
    print("ADAPTIVE-FLOOR DIAGNOSTIC (% of tracks where nominal threshold binds)")
    print("=" * 60)
    print_matrix(results, 'binding_pct', "{:.0f}%")

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
    for r, mf in frontier:
        c = results[(r, mf)]
        print(f"    rms={r:<7} min_frames={mf:<3} "
              f"det={c['detection_yield']:.1f}%  mean={c['mean_dev']:.2f}c")

    print("\n" + "-" * 50)
    print("OPTIMAL REGION")
    print("-" * 50)
    best_det = max(c['detection_yield'] for c in results.values())
    best_mean = min(c['mean_dev'] for c in results.values() if not np.isnan(c['mean_dev']))
    print(f"  Best detection yield anywhere in grid: {best_det:.1f}%")
    print(f"  Best mean |dev| anywhere in grid:      {best_mean:.2f} cents")
    print(f"  Cells within {YIELD_TOL} pp of best yield AND {DEV_TOL} c of best mean: {len(optimal)}")
    for r, mf in optimal:
        c = results[(r, mf)]
        marker = "  <-- Engine Optimal Default" if (
            r == PYIN_PARAMS['rms_threshold'] and mf == PYIN_PARAMS['min_frames']
        ) else ""
        print(f"    rms={r:<7} min_frames={mf:<3} "
              f"det={c['detection_yield']:.1f}%  mean={c['mean_dev']:.2f}c{marker}")

    print("\n" + "-" * 50)
    print("MARGINAL EFFECTS (range across the grid)")
    print("-" * 50)
    for name, grid, key_idx in [("rms_threshold", RMS_GRID, 0),
                                ("min_frames", MIN_FRAMES_GRID, 1)]:
        dets, means = [], []
        for v in grid:
            sel = [c for k, c in results.items() if k[key_idx] == v]
            dets.append(np.mean([c['detection_yield'] for c in sel]))
            means.append(np.mean([c['mean_dev'] for c in sel]))
        print(f"  {name:<16} detection yield spans {max(dets) - min(dets):.2f} pp, "
              f"mean |dev| spans {max(means) - min(means):.2f} c")

    generate_report(results, optimal, frontier, tracks, n_processed)

    print(f"\n[+] Report saved to {REPORT_PATH}")
    print("=" * 60)


def print_matrix(results, field, fmt):
    header = "  rms \\ mf   " + "".join(f"{mf:>10}" for mf in MIN_FRAMES_GRID)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in RMS_GRID:
        row = f"  {r:>11}  "
        for mf in MIN_FRAMES_GRID:
            v = results[(r, mf)][field]
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
    valid = {k: c for k, c in results.items() if not np.isnan(c['mean_dev'])}
    if not valid:
        return []
    best_det = max(c['detection_yield'] for c in valid.values())
    best_mean = min(c['mean_dev'] for c in valid.values())
    return sorted(
        k for k, c in valid.items()
        if c['detection_yield'] >= best_det - yield_tol
        and c['mean_dev'] <= best_mean + dev_tol
    )


def pareto_frontier(results):
    """Cells not dominated on both detection yield (max) and mean |dev| (min)."""
    valid = {k: c for k, c in results.items() if not np.isnan(c['mean_dev'])}
    front = []
    for k, c in valid.items():
        dominated = any(
            o['detection_yield'] >= c['detection_yield']
            and o['mean_dev'] <= c['mean_dev']
            and (o['detection_yield'] > c['detection_yield'] or o['mean_dev'] < c['mean_dev'])
            for o in valid.values()
        )
        if not dominated:
            front.append(k)
    return sorted(front)


def ci_matrix_table(results, prefix, fmt="{:.1f}"):
    """Matrix of `mean [lo, hi]` cells for a per-track statistic."""
    lines = []
    lines.append("| `rms_threshold` | " + " | ".join(f"$m = {mf}$" for mf in MIN_FRAMES_GRID) + " |")
    lines.append("| :---: |" + " :---: |" * len(MIN_FRAMES_GRID))
    for r in RMS_GRID:
        cells = []
        for mf in MIN_FRAMES_GRID:
            c = results[(r, mf)]
            m, lo, hi = c[f'{prefix}_mean'], c[f'{prefix}_ci_lo'], c[f'{prefix}_ci_hi']
            cells.append("—" if np.isnan(m)
                         else f"{fmt.format(m)} [{fmt.format(lo)}, {fmt.format(hi)}]")
        lines.append(f"| `{r}` | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def matrix_table(results, field, fmt):
    lines = []
    lines.append("| `rms_threshold` | " + " | ".join(f"$m = {mf}$" for mf in MIN_FRAMES_GRID) + " |")
    lines.append("| :---: |" + " :---: |" * len(MIN_FRAMES_GRID))
    for r in RMS_GRID:
        cells = []
        for mf in MIN_FRAMES_GRID:
            v = results[(r, mf)][field]
            cells.append("—" if np.isnan(v) else fmt.format(v))
        lines.append(f"| `{r}` | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def generate_report(results, optimal, frontier, tracks, n_processed):
    lines = []
    lines.append("# RMS Threshold & Minimum Duration Ablation Study")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # --- Methodology ---
    lines.append("## Methodology")
    lines.append("")
    lines.append("The pYIN engine was run through the full production pipeline "
                 "(extract → intonation filters → DTW alignment → harmonic folding → metrics) "
                 f"over a full factorial grid of {len(RMS_GRID)} `rms_threshold` values × "
                 f"{len(MIN_FRAMES_GRID)} `min_frames` values "
                 f"({len(RMS_GRID) * len(MIN_FRAMES_GRID)} combinations). All other "
                 "parameters were held at Engine Optimal Defaults "
                 f"(`max_pitch_slope=0.50`, `switch_prob=0.005`, "
                 f"`reference_pitch_hz={REFERENCE_PITCH_HZ}`).")
    lines.append("")
    lines.append("Both parameters are consumed **downstream** of `librosa.pyin()`, inside "
                 "`analyze_intonation()`. The pitch extraction was therefore performed exactly "
                 f"once per track and reused across all {len(RMS_GRID) * len(MIN_FRAMES_GRID)} "
                 f"cells — {len(tracks)} extractions rather than "
                 f"{len(tracks) * len(RMS_GRID) * len(MIN_FRAMES_GRID)}. The grid is exact, "
                 "not approximated.")
    lines.append("")
    counts = instrument_counts(tracks)
    lines.append(f"**Corpus.** The sweep covers **every** bowed-string track in the URMP corpus — "
                 f"{len(tracks)} stems "
                 f"({', '.join(f'{n} {inst.lower()}' for inst, n in sorted(counts.items()))}), "
                 f"{n_processed} of which yielded a strictly resolvable MIDI part — the same set "
                 "the slope/`switch_prob` ablation uses, so the two studies are directly "
                 "comparable. There is no track subset and therefore no sampling choice to justify.")
    lines.append("")
    lines.append("Each cell is summarised two ways. The **pooled** figure treats the corpus as one "
                 "note population; the **per-track** figure averages the track-level statistic and "
                 "carries a 95% confidence interval, taking the track rather than the note as the "
                 "unit of replication.")
    lines.append("")
    lines.append("**Metrics per cell:**")
    lines.append("")
    lines.append("- **Detection yield** — % of MIDI reference notes receiving a non-NaN `Deviation_Cents`.")
    lines.append("- **Inclusion yield** — % of *detected* notes surviving `is_note_excluded()` "
                 "($|\\text{dev}| \\le 100$ c and no harmonic-folding correction).")
    lines.append("- **Median / Mean / P90 $|\\text{Deviation\\_Cents}|$** — over included notes only.")
    lines.append("- **RMS gate rate** — % of voiced frames removed by the amplitude gate, measured "
                 "in isolation from the duration and DTW stages.")
    lines.append("- **Island destruction rate** — % of candidate note-islands (contiguous runs in "
                 "the combined mask) shorter than `min_frames` and therefore destroyed outright by "
                 "the duration filter.")
    lines.append("")

    # --- Adaptive floor caveat ---
    lines.append("### Adaptive Noise Floor")
    lines.append("")
    lines.append("`analyze_intonation()` does not use the nominal `rms_threshold` directly. It "
                 "applies an adaptive rule:")
    lines.append("")
    lines.append("$$\\tau_{\\text{eff}} = \\max\\left(\\tau_{\\text{nominal}},\\ "
                 "2 \\cdot P_{10}(\\text{RMS})\\right)$$")
    lines.append("")
    lines.append("The swept parameter is therefore only *binding* on tracks where it exceeds twice "
                 "the track's 10th-percentile RMS; below that the adaptive floor governs and the "
                 "nominal value has no effect at all. The **binding rate** — the % of tracks on "
                 "which the nominal threshold is the operative one — is reported below and is "
                 "essential to interpreting the sweep.")
    lines.append("")

    # --- Tracks ---
    lines.append("## Corpus")
    lines.append("")
    lines.append("| # | Track | Instrument |")
    lines.append("| :---: | :--- | :---: |")
    for i, t in enumerate(tracks, 1):
        lines.append(f"| {i} | {t['stem']} | {t['instrument']} |")
    lines.append("")

    # --- Matrices ---
    lines.append("## Detection Yield (%), pooled over all notes")
    lines.append("")
    lines.extend(matrix_table(results, 'detection_yield', "{:.1f}"))

    lines.append("## Detection Yield (%), per-track mean with 95% CI")
    lines.append("")
    lines.extend(ci_matrix_table(results, 'track_det_yield'))
    any_cell = results[next(iter(results))]
    widths = [c['track_det_yield_ci_hi'] - c['track_det_yield_ci_lo']
              for c in results.values() if not np.isnan(c['track_det_yield_ci_lo'])]
    det_spread = (max(c['track_det_yield_mean'] for c in results.values())
                  - min(c['track_det_yield_mean'] for c in results.values()))
    lines.append("> [!NOTE]")
    lines.append(f"> Intervals are over the {any_cell['n_tracks_ci']} tracks of the corpus, not "
                 f"over notes. The mean interval width is {np.mean(widths):.1f} pp, against a "
                 f"{det_spread:.1f} pp spread between the best and worst cells in the grid. "
                 + ("Every cell-to-cell difference in this study is therefore smaller than the "
                    "between-performance spread; no ranking within the grid should be read as "
                    "more than a tie-break."
                    if np.mean(widths) >= det_spread else
                    "Differences exceeding the interval width are resolvable against the "
                    "between-performance spread; smaller ones are not."))
    lines.append("")

    lines.append("## Inclusion Yield (% of detected)")
    lines.append("")
    lines.extend(matrix_table(results, 'inclusion_yield', "{:.1f}"))

    lines.append("## Median $|\\text{Deviation\\_Cents}|$ (included notes)")
    lines.append("")
    lines.extend(matrix_table(results, 'median_dev', "{:.2f}"))

    n_distinct = len({round(c['median_dev'], 6) for c in results.values()
                      if not np.isnan(c['median_dev'])})
    lines.append("> [!IMPORTANT]")
    lines.append(f"> The median takes only **{n_distinct}** distinct value(s) across all "
                 f"{len(results)} grid cells. `librosa.pyin()` quantises $f_0$ onto a grid of "
                 f"`resolution = 0.1` semitones, so every `Deviation_Cents` value is a multiple "
                 f"of {PYIN_RESOLUTION_CENTS:.0f} cents and the median collapses onto that grid. "
                 "The median is therefore **not** a usable discriminator at this scale; "
                 "**mean $|\\text{dev}|$ is used as the accuracy axis** for identifying the "
                 "optimal region. This reproduces the finding of the slope/`switch_prob` ablation.")
    lines.append("")

    lines.append("## Mean $|\\text{Deviation\\_Cents}|$ (included notes), pooled")
    lines.append("")
    lines.extend(matrix_table(results, 'mean_dev', "{:.2f}"))

    lines.append("## Mean $|\\text{Deviation\\_Cents}|$, per-track mean with 95% CI")
    lines.append("")
    lines.extend(ci_matrix_table(results, 'track_mean_dev', "{:.2f}"))

    lines.append("## 90th Percentile $|\\text{Deviation\\_Cents}|$ (included notes)")
    lines.append("")
    lines.extend(matrix_table(results, 'p90_dev', "{:.2f}"))

    lines.append("## RMS Gate Rate (% of voiced frames removed)")
    lines.append("")
    lines.extend(matrix_table(results, 'rms_gate_pct', "{:.2f}"))

    lines.append("## Adaptive-Floor Binding Rate (% of tracks where $\\tau_{nominal}$ is operative)")
    lines.append("")
    lines.extend(matrix_table(results, 'binding_pct', "{:.0f}"))

    lines.append("## Mean Effective Threshold $\\tau_{\\text{eff}}$")
    lines.append("")
    lines.extend(matrix_table(results, 'mean_effective_threshold', "{:.5f}"))
    lines.append("This is the axis the sweep actually traverses. Where the mean effective threshold "
                 "sits above the nominal value in the row label, the adaptive floor — not the swept "
                 "parameter — is what gated the frames, and the corresponding row of every table "
                 "above is measuring the floor rather than `rms_threshold`.")
    lines.append("")
    per_rms = []
    for r in RMS_GRID:
        c = results[(r, MIN_FRAMES_GRID[0])]
        per_rms.append((r, c['binding_pct'], c['mean_effective_threshold'],
                        c['min_effective_threshold'], c['max_effective_threshold']))
    lines.append("| Nominal $\\tau$ | Binding on | Mean $\\tau_{\\text{eff}}$ | Min $\\tau_{\\text{eff}}$ | Max $\\tau_{\\text{eff}}$ |")
    lines.append("| :---: | :---: | :---: | :---: | :---: |")
    for r, bind, m, lo, hi in per_rms:
        lines.append(f"| `{r}` | {bind:.0f}% of tracks | {m:.5f} | {lo:.5f} | {hi:.5f} |")
    lines.append("")
    inert = [r for r, bind, *_ in per_rms if bind == 0]
    if inert:
        lines.append(f"The nominal threshold is **entirely inert** at "
                     f"{', '.join(f'`{r}`' for r in inert)} — on no track in the corpus does it "
                     "exceed twice the 10th-percentile RMS. The pipeline is deterministic, so those "
                     "rows are not merely similar but **identical**: they all ran at the same "
                     "adaptive floor. Reading them as a sensitivity curve for `rms_threshold` "
                     "would be reading an axis the sweep never moved along.")
        lines.append("")

    lines.append("## Duration Filter: Islands Destroyed (% of candidate islands)")
    lines.append("")
    lines.extend(matrix_table(results, 'island_destroy_pct', "{:.2f}"))

    lines.append("## Duration Filter: Frames Lost (% of candidate island frames)")
    lines.append("")
    lines.extend(matrix_table(results, 'island_frame_loss_pct', "{:.2f}"))

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
    for name, grid, key_idx in [("`rms_threshold`", RMS_GRID, 0),
                                ("`min_frames`", MIN_FRAMES_GRID, 1)]:
        dets, means = [], []
        for v in grid:
            sel = [c for k, c in results.items() if k[key_idx] == v]
            dets.append(np.mean([c['detection_yield'] for c in sel]))
            means.append(np.mean([c['mean_dev'] for c in sel]))
        lines.append(f"| {name} | {max(dets) - min(dets):.2f} pp | {max(means) - min(means):.2f} c |")
    lines.append("")

    # --- Pareto frontier ---
    lines.append("## Pareto Frontier")
    lines.append("")
    lines.append("Cells not dominated on both axes (higher detection yield **and** lower "
                 "mean $|\\text{dev}|$):")
    lines.append("")
    lines.append("| `rms_threshold` | `min_frames` | Detection Yield | Mean \\|dev\\| (c) |")
    lines.append("| :---: | :---: | :---: | :---: |")
    for r, mf in frontier:
        c = results[(r, mf)]
        lines.append(f"| {r} | {mf} | {c['detection_yield']:.1f}% | {c['mean_dev']:.2f} |")
    lines.append("")

    # --- Optimal region ---
    lines.append("## Optimal Region")
    lines.append("")
    valid = {k: c for k, c in results.items() if not np.isnan(c['mean_dev'])}
    if valid:
        best_det = max(c['detection_yield'] for c in valid.values())
        best_mean = min(c['mean_dev'] for c in valid.values())
        lines.append(f"- **Maximum detection yield in grid**: {best_det:.1f}%")
        lines.append(f"- **Minimum mean $|\\text{{dev}}|$ in grid**: {best_mean:.2f} cents")
        lines.append("")
        lines.append(f"The optimal region is defined as those cells simultaneously within "
                     f"{YIELD_TOL} percentage point of the maximum detection yield **and** within "
                     f"{DEV_TOL} cent of the minimum mean deviation — the flat plateau of the "
                     f"yield/accuracy trade-off.")
        lines.append("")
        lines.append("| `rms_threshold` | `min_frames` | Detection Yield | Inclusion Yield | Mean \\|dev\\| (c) | Islands Destroyed |")
        lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
        for r, mf in optimal:
            c = results[(r, mf)]
            note = " **(Engine Optimal Default)**" if (
                r == PYIN_PARAMS['rms_threshold'] and mf == PYIN_PARAMS['min_frames']
            ) else ""
            lines.append(f"| {r}{note} | {mf} | {c['detection_yield']:.1f}% "
                         f"| {c['inclusion_yield']:.1f}% | {c['mean_dev']:.2f} "
                         f"| {c['island_destroy_pct']:.2f}% |")
        lines.append("")

        default_key = (PYIN_PARAMS['rms_threshold'], PYIN_PARAMS['min_frames'])
        d = results.get(default_key)
        if d:
            lines.append("### Production Setting vs. Grid")
            lines.append("")
            lines.append(f"The production configuration (`rms_threshold=0.005`, `min_frames=2`) "
                         f"achieves {d['detection_yield']:.1f}% detection yield, "
                         f"{d['inclusion_yield']:.1f}% inclusion yield, and a mean "
                         f"$|\\text{{dev}}|$ of {d['mean_dev']:.2f} cents "
                         f"({d['included']} included notes) — "
                         f"{'inside' if default_key in optimal else 'outside'} the optimal region. "
                         f"Per track that is a detection yield of "
                         f"{d['track_det_yield_mean']:.1f}% "
                         f"(95% CI [{d['track_det_yield_ci_lo']:.1f}, "
                         f"{d['track_det_yield_ci_hi']:.1f}]) over {d['n_tracks_ci']} tracks. "
                         f"The nominal RMS threshold is binding on "
                         f"{d['binding_pct']:.0f}% of tracks (mean effective threshold "
                         f"{d['mean_effective_threshold']:.5f}).")
            lines.append("")
            for label, key in [
                ("REAPER's `min_frames=4` at the same RMS threshold",
                 (PYIN_PARAMS['rms_threshold'], 4)),
                ("no duration filtering (`min_frames=1`)",
                 (PYIN_PARAMS['rms_threshold'], 1)),
                ("the loosest amplitude gate (`rms_threshold=0.001`)",
                 (0.001, PYIN_PARAMS['min_frames'])),
                ("the tightest amplitude gate (`rms_threshold=0.05`)",
                 (0.05, PYIN_PARAMS['min_frames'])),
            ]:
                o = results.get(key)
                if o:
                    lines.append(f"- Against {label}: detection yield "
                                 f"{o['detection_yield']:.1f}% "
                                 f"($\\Delta = {d['detection_yield'] - o['detection_yield']:+.2f}$ pp), "
                                 f"mean $|\\text{{dev}}|$ {o['mean_dev']:.2f} c "
                                 f"($\\Delta = {d['mean_dev'] - o['mean_dev']:+.2f}$ c), "
                                 f"inclusion yield {o['inclusion_yield']:.1f}% "
                                 f"($\\Delta = {d['inclusion_yield'] - o['inclusion_yield']:+.2f}$ pp).")
            lines.append("")
    else:
        lines.append("No cell produced any included notes.")
        lines.append("")

    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    main()

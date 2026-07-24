"""
Gross Error Exclusion Threshold Justification
==============================================
Empirical analysis of the 100-cent exclusion threshold used by
is_note_excluded() in the Hello-Audio pipeline.

Runs pYIN (Engine Optimal Defaults) on all URMP bowed-string tracks,
collects per-note Deviation_Cents, and reports:
  - Distribution of |Deviation_Cents| across threshold levels
  - Sensitivity comparison (50c / 100c / 200c)
  - Per-instrument breakdown of excluded notes
  - Histogram bin counts

Usage:
    python tests/scripts/validation/validate_exclusion_threshold.py
"""

import os
import sys
import gc
import numpy as np
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics

REPORT_PATH = os.path.join(SCRIPT_DIR, 'exclusion_threshold_report.md')

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

THRESHOLDS = [25, 50, 75, 100, 150, 200]

HISTOGRAM_BINS = [0, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200, 500, 1200]


def run_pipeline(audio_path, midi_notes, instrument):
    with open(audio_path, 'rb') as af:
        y, sr, f0, voiced_flag, rms, _ = extract_pitch_and_rms(
            af,
            instrument=instrument,
            switch_prob=PYIN_PARAMS['switch_prob'],
            enable_freq_limits=TOGGLES['freq_limits'],
            pitch_engine="pYIN"
        )

    res = analyze_intonation(
        y, sr, f0, voiced_flag, rms,
        rms_threshold=PYIN_PARAMS['rms_threshold'],
        min_frames=PYIN_PARAMS['min_frames'],
        max_pitch_slope=PYIN_PARAMS['max_pitch_slope'],
        toggles=TOGGLES
    )
    final_mask = res['final_mask']

    time_array, expected, warped, _, folded_f0_hz, _, _, correction_array = process_dtw_alignment(
        midi_notes, f0, y, sr, final_mask, TOGGLES, PYIN_PARAMS['max_pitch_slope']
    )

    dtw_metrics = calculate_dtw_metrics(
        midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
    )

    del y, sr, f0, voiced_flag, rms, final_mask, time_array, expected, warped, folded_f0_hz, correction_array
    gc.collect()

    return dtw_metrics


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


def main():
    print("=" * 60)
    print("Gross Error Exclusion Threshold Justification")
    print("Engine: pYIN | Engine Optimal Defaults")
    print("Threshold under test: |Deviation_Cents| > 100 cents")
    print("=" * 60)

    dataset_dir = Path(os.path.join(PROJECT_ROOT, 'dataset (Strings only)'))
    if not dataset_dir.exists():
        print(f"Error: Dataset not found at {dataset_dir}")
        sys.exit(1)

    tracks = discover_tracks(dataset_dir)
    print(f"\n[INFO] Found {len(tracks)} string tracks to process.\n")

    if not tracks:
        print("No tracks found. Exiting.")
        sys.exit(1)

    all_abs_devs = []
    all_instruments = []
    all_correction_applied = []
    total_midi_notes = 0
    total_detected = 0
    total_missed = 0
    per_track_results = []

    for i, t in enumerate(tracks, 1):
        stem = t['stem']
        instrument = t['instrument']
        print(f"[{i}/{len(tracks)}] {stem} ({instrument})", flush=True)

        with open(t['midi_path'], 'rb') as f:
            midi_notes = parse_midi_with_timing(f, target_track=t['target_track'])
            if not midi_notes:
                f.seek(0)
                midi_notes = parse_midi_with_timing(f, target_track=0)
            if not midi_notes:
                f.seek(0)
                midi_notes = parse_midi_with_timing(f, target_track=1)

        if not midi_notes:
            print(f"  [!] No MIDI notes found, skipping")
            continue

        n_midi = len(midi_notes)
        total_midi_notes += n_midi

        metrics = run_pipeline(t['audio_path'], midi_notes, instrument)

        track_detected = 0
        track_missed = 0
        track_abs_devs = []

        for m in metrics:
            dev = m.get('Deviation_Cents', float('nan'))
            corr = m.get('Correction_Applied', False)

            if np.isnan(dev):
                track_missed += 1
            else:
                track_detected += 1
                abs_dev = abs(dev)
                track_abs_devs.append(abs_dev)
                all_abs_devs.append(abs_dev)
                all_instruments.append(instrument)
                all_correction_applied.append(corr)

        total_detected += track_detected
        total_missed += track_missed

        exceed_100 = sum(1 for d in track_abs_devs if d > 100)
        pct_100 = (exceed_100 / len(track_abs_devs) * 100) if track_abs_devs else 0.0

        per_track_results.append({
            'stem': stem,
            'instrument': instrument,
            'n_midi': n_midi,
            'detected': track_detected,
            'missed': track_missed,
            'exceed_100': exceed_100,
            'pct_exceed_100': pct_100,
        })

        print(f"  Detected: {track_detected}/{n_midi}  |dev|>100c: {exceed_100} ({pct_100:.1f}%)")

    all_abs_devs = np.array(all_abs_devs)
    all_instruments = np.array(all_instruments)
    all_correction_applied = np.array(all_correction_applied)

    # --- Threshold sensitivity ---
    print("\n" + "=" * 60)
    print("THRESHOLD SENSITIVITY")
    print("=" * 60)

    threshold_stats = {}
    for thresh in THRESHOLDS:
        n_exceed = int(np.sum(all_abs_devs > thresh))
        pct = n_exceed / len(all_abs_devs) * 100
        threshold_stats[thresh] = (n_exceed, pct)
        print(f"  |dev| > {thresh:>3d}c:  {n_exceed:>5d} / {len(all_abs_devs)}  ({pct:.2f}%)")

    # --- Histogram ---
    print("\n" + "-" * 50)
    print("DEVIATION DISTRIBUTION (histogram)")
    print("-" * 50)

    hist_counts, _ = np.histogram(all_abs_devs, bins=HISTOGRAM_BINS)
    for j in range(len(hist_counts)):
        lo = HISTOGRAM_BINS[j]
        hi = HISTOGRAM_BINS[j + 1]
        pct = hist_counts[j] / len(all_abs_devs) * 100
        print(f"  [{lo:>4d}, {hi:>4d})c:  {hist_counts[j]:>5d}  ({pct:.1f}%)")

    # --- Per-instrument breakdown of >100c notes ---
    print("\n" + "-" * 50)
    print("NOTES EXCEEDING 100 CENTS — BY INSTRUMENT")
    print("-" * 50)

    exceed_mask = all_abs_devs > 100
    inst_breakdown = {}
    for inst in ["Violin", "Viola", "Cello"]:
        inst_mask = all_instruments == inst
        inst_total = int(np.sum(inst_mask))
        inst_exceed = int(np.sum(exceed_mask & inst_mask))
        inst_exceed_corr = int(np.sum(exceed_mask & inst_mask & all_correction_applied))
        inst_breakdown[inst] = {
            'total': inst_total,
            'exceed': inst_exceed,
            'exceed_pct': (inst_exceed / inst_total * 100) if inst_total > 0 else 0.0,
            'exceed_with_corr': inst_exceed_corr,
        }
        print(f"  {inst:>8s}: {inst_exceed:>4d} / {inst_total:>5d} ({inst_breakdown[inst]['exceed_pct']:.2f}%)"
              f"  — Correction_Applied: {inst_exceed_corr}")

    # --- Summary stats ---
    print("\n" + "-" * 50)
    print("SUMMARY STATISTICS (detected notes)")
    print("-" * 50)
    print(f"  Total MIDI notes:   {total_midi_notes}")
    print(f"  Detected:           {total_detected}")
    print(f"  Missed (NaN):       {total_missed}")
    print(f"  Median |dev|:       {np.median(all_abs_devs):.2f} cents")
    print(f"  Mean |dev|:         {np.mean(all_abs_devs):.2f} cents")
    print(f"  90th percentile:    {np.percentile(all_abs_devs, 90):.2f} cents")
    print(f"  95th percentile:    {np.percentile(all_abs_devs, 95):.2f} cents")
    print(f"  99th percentile:    {np.percentile(all_abs_devs, 99):.2f} cents")
    print(f"  Max |dev|:          {np.max(all_abs_devs):.2f} cents")

    # --- Generate report ---
    generate_report(
        total_midi_notes, total_detected, total_missed,
        all_abs_devs, threshold_stats, hist_counts,
        inst_breakdown, per_track_results
    )

    print(f"\n[+] Report saved to {REPORT_PATH}")
    print("=" * 60)


def generate_report(total_midi, total_detected, total_missed,
                    all_abs_devs, threshold_stats, hist_counts,
                    inst_breakdown, per_track_results):
    lines = []
    lines.append("# Gross Error Exclusion Threshold Justification")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # --- Methodology ---
    lines.append("## Methodology")
    lines.append("")
    lines.append("The pYIN pitch engine was run through the full production pipeline "
                 "(extract → intonation filters → DTW alignment → harmonic folding → metrics) "
                 "on all bowed-string tracks in the URMP dataset using Engine Optimal Default "
                 "parameters (switch_prob=0.005, rms_threshold=0.005, min_frames=2, "
                 "max_pitch_slope=0.50). For each detected note, the absolute value of "
                 "`Deviation_Cents` was collected to characterize the empirical deviation "
                 "distribution and evaluate the sensitivity of the 100-cent exclusion threshold.")
    lines.append("")

    # --- Detection summary ---
    lines.append("## Detection Summary")
    lines.append("")
    lines.append(f"- **Total MIDI notes**: {total_midi}")
    lines.append(f"- **Detected**: {total_detected} ({total_detected / total_midi * 100:.1f}%)")
    lines.append(f"- **Missed (NaN)**: {total_missed} ({total_missed / total_midi * 100:.1f}%)")
    lines.append("")

    # --- Distribution stats ---
    lines.append("## Deviation Distribution (Detected Notes)")
    lines.append("")
    lines.append(f"- **Median $|\\text{{dev}}|$**: {np.median(all_abs_devs):.2f} cents")
    lines.append(f"- **Mean $|\\text{{dev}}|$**: {np.mean(all_abs_devs):.2f} cents")
    lines.append(f"- **90th percentile**: {np.percentile(all_abs_devs, 90):.2f} cents")
    lines.append(f"- **95th percentile**: {np.percentile(all_abs_devs, 95):.2f} cents")
    lines.append(f"- **99th percentile**: {np.percentile(all_abs_devs, 99):.2f} cents")
    lines.append(f"- **Maximum**: {np.max(all_abs_devs):.2f} cents")
    lines.append("")

    # --- Threshold sensitivity ---
    lines.append("## Threshold Sensitivity")
    lines.append("")
    lines.append("| Threshold (cents) | Notes Exceeding | % of Detected |")
    lines.append("| :---: | :---: | :---: |")
    for thresh in THRESHOLDS:
        n, pct = threshold_stats[thresh]
        lines.append(f"| {thresh} | {n} | {pct:.2f}% |")
    lines.append("")

    # --- Histogram ---
    lines.append("## Histogram of $|\\text{Deviation\\_Cents}|$")
    lines.append("")
    lines.append("| Bin (cents) | Count | % of Detected |")
    lines.append("| :---: | :---: | :---: |")
    for j in range(len(hist_counts)):
        lo = HISTOGRAM_BINS[j]
        hi = HISTOGRAM_BINS[j + 1]
        pct = hist_counts[j] / len(all_abs_devs) * 100
        lines.append(f"| [{lo}, {hi}) | {hist_counts[j]} | {pct:.1f}% |")
    lines.append("")

    # --- Per-instrument breakdown ---
    lines.append("## Notes Exceeding 100 Cents — Per Instrument")
    lines.append("")
    lines.append("| Instrument | Total Detected | Exceeding 100c | % Excluded | With Correction_Applied |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for inst in ["Violin", "Viola", "Cello"]:
        d = inst_breakdown[inst]
        lines.append(f"| {inst} | {d['total']} | {d['exceed']} | {d['exceed_pct']:.2f}% | {d['exceed_with_corr']} |")
    lines.append("")

    # --- Per-track table ---
    lines.append("## Per-Track Breakdown")
    lines.append("")
    lines.append("| Track | Instrument | MIDI Notes | Detected | Missed | >100c | % >100c |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    for t in per_track_results:
        lines.append(f"| {t['stem']} | {t['instrument']} | {t['n_midi']} | {t['detected']} "
                     f"| {t['missed']} | {t['exceed_100']} | {t['pct_exceed_100']:.1f}% |")
    lines.append("")

    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    main()

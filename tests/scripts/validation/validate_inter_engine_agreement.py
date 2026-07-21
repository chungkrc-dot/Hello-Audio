"""
Inter-Engine Agreement on Real Audio (URMP)
============================================
Compares pYIN and REAPER pitch tracking on real bowed-string recordings
from the URMP dataset. For each track, both engines run the full pipeline
with Engine Optimal Default parameters, and their per-note Deviation_Cents
results are paired by Note_Index.

Reports: Pearson r, MAD, Bland-Altman statistics, per-track breakdown,
and detection yield comparison.

Usage:
    python tests/scripts/validation/validate_inter_engine_agreement.py
"""

import os
import sys
import gc
import numpy as np
import warnings
from pathlib import Path
from scipy import stats
from datetime import datetime

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded

REPORT_PATH = os.path.join(SCRIPT_DIR, 'inter_engine_agreement_report.md')

ENGINES = {
    "pYIN":   {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 2, "switch_prob": 0.005},
    "REAPER": {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 4, "switch_prob": 0.005},
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
STRING_INSTRUMENTS = set(INST_MAP.values())


def run_pipeline(audio_path, midi_notes, instrument, engine, params):
    with open(audio_path, 'rb') as af:
        y, sr, f0, voiced_flag, rms, _ = extract_pitch_and_rms(
            af,
            instrument=instrument,
            switch_prob=params['switch_prob'],
            enable_freq_limits=TOGGLES['freq_limits'],
            pitch_engine=engine
        )

    res = analyze_intonation(
        y, sr, f0, voiced_flag, rms,
        rms_threshold=params['rms_threshold'],
        min_frames=params['min_frames'],
        max_pitch_slope=params['max_pitch_slope'],
        toggles=TOGGLES
    )
    final_mask = res['final_mask']

    time_array, expected, warped, _, folded_f0_hz, _, _, correction_array = process_dtw_alignment(
        midi_notes, f0, y, sr, final_mask, TOGGLES, params['max_pitch_slope']
    )

    dtw_metrics = calculate_dtw_metrics(
        midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
    )

    del y, sr, f0, voiced_flag, rms, final_mask, time_array, expected, warped, folded_f0_hz, correction_array
    gc.collect()

    return dtw_metrics


def pair_deviations(pyin_metrics, reaper_metrics):
    pyin_by_idx = {m['Note_Index']: m for m in pyin_metrics}
    reaper_by_idx = {m['Note_Index']: m for m in reaper_metrics}

    pyin_devs = []
    reaper_devs = []

    common_indices = sorted(set(pyin_by_idx) & set(reaper_by_idx))
    for idx in common_indices:
        p = pyin_by_idx[idx]
        r = reaper_by_idx[idx]

        p_dev = p.get('Deviation_Cents', float('nan'))
        r_dev = r.get('Deviation_Cents', float('nan'))

        if np.isnan(p_dev) or np.isnan(r_dev):
            continue
        if is_note_excluded(p) or is_note_excluded(r):
            continue

        pyin_devs.append(p_dev)
        reaper_devs.append(r_dev)

    return np.array(pyin_devs), np.array(reaper_devs)


def detection_yield(metrics, total_midi_notes):
    detected = sum(1 for m in metrics if not np.isnan(m.get('Deviation_Cents', float('nan'))))
    return detected, total_midi_notes, (detected / total_midi_notes * 100) if total_midi_notes > 0 else 0.0


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
    print("Inter-Engine Agreement on Real Audio (URMP)")
    print("Engines: pYIN vs REAPER | Engine Optimal Defaults")
    print("Exclusion: is_note_excluded() [|dev|>100c OR Correction]")
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

    all_pyin_devs = []
    all_reaper_devs = []
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

        total_midi = len(midi_notes)

        pyin_metrics = run_pipeline(t['audio_path'], midi_notes, instrument, "pYIN", ENGINES["pYIN"])
        reaper_metrics = run_pipeline(t['audio_path'], midi_notes, instrument, "REAPER", ENGINES["REAPER"])

        pyin_devs, reaper_devs = pair_deviations(pyin_metrics, reaper_metrics)

        pyin_det, _, pyin_yield = detection_yield(pyin_metrics, total_midi)
        reaper_det, _, reaper_yield = detection_yield(reaper_metrics, total_midi)

        track_result = {
            'stem': stem,
            'instrument': instrument,
            'total_midi': total_midi,
            'pyin_yield': pyin_yield,
            'reaper_yield': reaper_yield,
            'pyin_detected': pyin_det,
            'reaper_detected': reaper_det,
            'n_paired': len(pyin_devs),
        }

        if len(pyin_devs) >= 3:
            r, p = stats.pearsonr(pyin_devs, reaper_devs)
            mad = np.mean(np.abs(pyin_devs - reaper_devs))
            track_result['r'] = r
            track_result['p'] = p
            track_result['mad'] = mad
            print(f"  Paired: {len(pyin_devs)} notes  r={r:.4f}  MAD={mad:.2f}c  "
                  f"Yield: pYIN={pyin_yield:.1f}% REAPER={reaper_yield:.1f}%")
        else:
            track_result['r'] = None
            track_result['p'] = None
            track_result['mad'] = None
            print(f"  Insufficient pairs ({len(pyin_devs)}), skipping stats  "
                  f"Yield: pYIN={pyin_yield:.1f}% REAPER={reaper_yield:.1f}%")

        all_pyin_devs.extend(pyin_devs)
        all_reaper_devs.extend(reaper_devs)
        per_track_results.append(track_result)

    all_pyin = np.array(all_pyin_devs)
    all_reaper = np.array(all_reaper_devs)

    # --- Aggregate Statistics ---
    print("\n" + "=" * 60)
    print("AGGREGATE RESULTS")
    print("=" * 60)

    aggregate = {}

    if len(all_pyin) >= 3:
        r, p = stats.pearsonr(all_pyin, all_reaper)
        mad = np.mean(np.abs(all_pyin - all_reaper))

        diffs = all_pyin - all_reaper
        bias = np.mean(diffs)
        sd_diff = np.std(diffs, ddof=1)
        loa_lower = bias - 1.96 * sd_diff
        loa_upper = bias + 1.96 * sd_diff

        aggregate = {
            'r': r, 'p': p, 'mad': mad, 'n': len(all_pyin),
            'bias': bias, 'sd_diff': sd_diff,
            'loa_lower': loa_lower, 'loa_upper': loa_upper,
        }

        print(f"  Total paired notes: {len(all_pyin)}")
        print(f"  Pearson r = {r:.4f} (p = {p:.2e})")
        print(f"  MAD = {mad:.2f} cents")
        print(f"  Bland-Altman bias (pYIN − REAPER) = {bias:+.2f} cents")
        print(f"  95% Limits of Agreement: [{loa_lower:+.2f}, {loa_upper:+.2f}] cents")
    else:
        print("  Insufficient paired data for aggregate statistics.")

    # --- Per-instrument summary ---
    print("\n" + "-" * 50)
    print("PER-INSTRUMENT SUMMARY")
    print("-" * 50)

    for inst in ["Violin", "Viola", "Cello"]:
        inst_tracks = [t for t in per_track_results if t['instrument'] == inst]
        if not inst_tracks:
            continue
        rs = [t['r'] for t in inst_tracks if t['r'] is not None]
        mads = [t['mad'] for t in inst_tracks if t['mad'] is not None]
        n_tracks = len(inst_tracks)
        n_pairs = sum(t['n_paired'] for t in inst_tracks)
        mean_pyin_yield = np.mean([t['pyin_yield'] for t in inst_tracks])
        mean_reaper_yield = np.mean([t['reaper_yield'] for t in inst_tracks])

        print(f"\n  {inst} ({n_tracks} tracks, {n_pairs} paired notes):")
        if rs:
            print(f"    Median r = {np.median(rs):.4f}  Mean MAD = {np.mean(mads):.2f}c")
        print(f"    Mean yield: pYIN={mean_pyin_yield:.1f}%  REAPER={mean_reaper_yield:.1f}%")

    # --- Generate Report ---
    generate_report(aggregate, per_track_results)

    print(f"\n[+] Report saved to {REPORT_PATH}")
    print("=" * 60)


def generate_report(aggregate, per_track_results):
    lines = []
    lines.append("# Inter-Engine Agreement on Real Audio (URMP)")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("Both pYIN and REAPER ran the full production pipeline (extract → intonation "
                 "filters → DTW alignment → harmonic folding → metrics) on every bowed-string "
                 "track in the URMP dataset. Engine Optimal Default parameters were used for both "
                 "engines (switch_prob=0.005, rms_threshold=0.005, min_frames=2/4, "
                 "max_pitch_slope=0.50). Per-note `Deviation_Cents` results were paired by "
                 "`Note_Index`; notes excluded by `is_note_excluded()` (|dev| > 100 cents or "
                 "harmonic folding correction applied) or missed by either engine were dropped.")
    lines.append("")

    if aggregate:
        lines.append("## Aggregate Results")
        lines.append("")
        lines.append(f"- **Paired notes**: {aggregate['n']}")
        lines.append(f"- **Pearson $r$**: {aggregate['r']:.4f} ($p = {aggregate['p']:.2e}$)")
        lines.append(f"- **Mean Absolute Difference (MAD)**: {aggregate['mad']:.2f} cents")
        lines.append(f"- **Bland-Altman bias** (pYIN − REAPER): {aggregate['bias']:+.2f} cents")
        lines.append(f"- **95% Limits of Agreement**: [{aggregate['loa_lower']:+.2f}, {aggregate['loa_upper']:+.2f}] cents")
        lines.append(f"- **SD of differences**: {aggregate['sd_diff']:.2f} cents")
        lines.append("")
    else:
        lines.append("## Aggregate Results")
        lines.append("")
        lines.append("Insufficient paired data for aggregate statistics.")
        lines.append("")

    # Per-track table
    lines.append("## Per-Track Breakdown")
    lines.append("")
    lines.append("| Track | Instrument | MIDI Notes | Paired | Pearson r | MAD (c) | pYIN Yield | REAPER Yield |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for t in per_track_results:
        r_str = f"{t['r']:.4f}" if t['r'] is not None else "—"
        mad_str = f"{t['mad']:.2f}" if t['mad'] is not None else "—"
        lines.append(f"| {t['stem']} | {t['instrument']} | {t['total_midi']} | {t['n_paired']} "
                     f"| {r_str} | {mad_str} | {t['pyin_yield']:.1f}% | {t['reaper_yield']:.1f}% |")
    lines.append("")

    # Per-instrument summary
    lines.append("## Per-Instrument Summary")
    lines.append("")
    lines.append("| Instrument | Tracks | Paired Notes | Median r | Mean MAD (c) | Mean pYIN Yield | Mean REAPER Yield |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    for inst in ["Violin", "Viola", "Cello"]:
        inst_tracks = [t for t in per_track_results if t['instrument'] == inst]
        if not inst_tracks:
            continue
        rs = [t['r'] for t in inst_tracks if t['r'] is not None]
        mads = [t['mad'] for t in inst_tracks if t['mad'] is not None]
        n_pairs = sum(t['n_paired'] for t in inst_tracks)
        mean_pyin = np.mean([t['pyin_yield'] for t in inst_tracks])
        mean_reaper = np.mean([t['reaper_yield'] for t in inst_tracks])
        r_str = f"{np.median(rs):.4f}" if rs else "—"
        mad_str = f"{np.mean(mads):.2f}" if mads else "—"
        lines.append(f"| {inst} | {len(inst_tracks)} | {n_pairs} | {r_str} | {mad_str} "
                     f"| {mean_pyin:.1f}% | {mean_reaper:.1f}% |")
    lines.append("")

    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    main()

"""
diagnose_dtw_mode.py
--------------------
Diagnostic script to compare force_global=True vs force_global=False
on AuSep_2_vn_09_Jesus and other long/dense tracks.

Outputs:
  tests/batch_results/dtw_mode_comparison.csv    - summary per track/engine/mode
  tests/batch_results/dtw_mode_diagnostics.json  - per-note detail for 09_Jesus

Run: python3 tests/diagnose_dtw_mode.py
"""
import os
import sys
import numpy as np
import json
import warnings
warnings.filterwarnings('ignore')

# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing, get_midi_tempo
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded
import librosa

# ============================================================
# Tracks to test: 09_Jesus (primary) + other long/dense tracks
# for systematic comparison
# ============================================================
# These are tracks with >200 MIDI notes that showed yield drops
# in the new batch results vs old Appendix A
TARGET_TRACKS = [
    "AuSep_2_vn_09_Jesus",    # 486 notes, -19.75pp drop
    "AuSep_1_vn_35_Rondeau",  # 484 notes, -14.66pp drop
    "AuSep_1_vn_12_Spring",   # 432 notes, -22.92pp drop
    "AuSep_1_vn_26_King",     # 229 notes, -9.17pp drop
    "AuSep_2_vc_11_Maria",    # 362 notes, -5.52pp drop
    "AuSep_5_vc_44_K515",     # 360 notes, -9.72pp drop
    "AuSep_2_vn_44_K515",     # 477 notes, -5.87pp drop
    "AuSep_1_vn_32_Fugue",    # 244 notes, -4.51pp drop
    # Control: a short track that showed NO drop
    "AuSep_2_vn_13_Hark",     # 73 notes, identical yield
]

# Full per-note diagnostics only for the primary investigation target
FULL_DIAGNOSTIC_TRACKS = [
    "AuSep_2_vn_09_Jesus",
]

def main():
    print("=" * 70)
    print("DTW Mode Diagnostic: force_global=True vs force_global=False")
    print("=" * 70)

    dataset_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dataset'))
    output_dir = os.path.join(os.path.dirname(__file__), 'batch_results')
    os.makedirs(output_dir, exist_ok=True)

    out_csv = os.path.join(output_dir, 'dtw_mode_comparison.csv')
    out_json = os.path.join(output_dir, 'dtw_mode_diagnostics.json')

    # Engine parameters (matching Appendix A)
    engines = {
        "REAPER": {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 4, "switch_prob": 0.005},
        "pYIN":   {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 2, "switch_prob": 0.005},
    }

    # Write CSV header
    with open(out_csv, 'w') as f:
        f.write("Track,Engine,DTW_Mode,Total_Notes,Detected,Det_Yield,NaN_Count,"
                "Included,Inc_Yield,Mean_Dev_Hz,"
                "Corr_Applied_Count,Over100c_Count,"
                "NaN_FirstQuarter,NaN_SecondQuarter,NaN_ThirdQuarter,NaN_FourthQuarter\n")

    diagnostics = {}

    for stem in TARGET_TRACKS:
        # Find the audio file
        audio_path = None
        for root, dirs, files in os.walk(dataset_dir):
            for fname in files:
                if fname == stem + ".wav":
                    audio_path = os.path.join(root, fname)
                    break
            if audio_path:
                break

        if not audio_path:
            print(f"\n[!] Cannot find {stem}.wav in dataset — skipping")
            continue

        parent_dir = os.path.dirname(audio_path)
        midi_files = [f for f in os.listdir(parent_dir) if f.endswith('.mid')]
        if not midi_files:
            print(f"\n[!] No .mid file for {stem} — skipping")
            continue
        midi_path = os.path.join(parent_dir, midi_files[0])

        # Parse track index and instrument
        parts = stem.split('_')
        try:
            target_track = int(parts[1])
            inst_code = parts[2]
        except (IndexError, ValueError):
            print(f"\n[!] Cannot parse {stem} — skipping")
            continue

        inst_map = {"vn": "Violin", "va": "Viola", "vc": "Cello"}
        instrument_name = inst_map.get(inst_code, "Violin")

        print(f"\n{'='*70}")
        print(f"Processing: {stem} (Track {target_track}, {instrument_name})")
        print(f"{'='*70}")

        # Parse MIDI (full length, no cap)
        with open(midi_path, 'rb') as f:
            midi_notes = parse_midi_with_timing(f, target_track=target_track)
        if not midi_notes:
            print(f"  [!] No MIDI notes — skipping")
            continue

        total_notes = len(midi_notes)

        # Get track duration from MIDI
        last_end = max(n['End_Time'] if isinstance(n, dict) else getattr(n, 'End_Time', 0) for n in midi_notes)
        print(f"  MIDI notes: {total_notes}, MIDI duration: {last_end:.1f}s")

        bpm = get_midi_tempo(midi_path)
        print(f"  BPM: {bpm:.1f}")

        is_full_diag = stem in FULL_DIAGNOSTIC_TRACKS

        for engine_name, params in engines.items():
            print(f"\n  Engine: {engine_name}")

            # Extract pitch ONCE per engine (same audio for both DTW modes)
            with open(audio_path, 'rb') as af:
                y, sr, f0, voiced_flag, rms, _ = extract_pitch_and_rms(
                    af, instrument=instrument_name,
                    switch_prob=params['switch_prob'],
                    enable_freq_limits=True,
                    pitch_engine=engine_name
                )

            # Generate final_mask via analyze_intonation (same for both modes)
            res = analyze_intonation(
                y, sr, f0, voiced_flag, rms,
                rms_threshold=params['rms_threshold'],
                min_frames=params['min_frames'],
                max_pitch_slope=params['max_pitch_slope'],
                toggles={
                    "freq_limits": True, "slope_filter": True,
                    "duration_filter": True, "locked_target": True,
                    "harmonic_folding": True
                }
            )
            final_mask = res['final_mask']

            for mode_name, force_global_val in [("global", True), ("subsequence", False)]:
                print(f"    DTW mode: {mode_name} (force_global={force_global_val})")

                toggles = {
                    "freq_limits": True, "slope_filter": True,
                    "duration_filter": True, "locked_target": True,
                    "harmonic_folding": True,
                    "force_global": force_global_val,
                }

                time_array, expected, warped, expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask, correction_array = process_dtw_alignment(
                    midi_notes, f0, y, sr, final_mask, toggles, params['max_pitch_slope']
                )

                dtw_metrics = calculate_dtw_metrics(
                    midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
                )

                if not dtw_metrics:
                    print(f"      [!] No metrics returned")
                    continue

                # Compute yields
                detected = [n for n in dtw_metrics if not np.isnan(n.get('Deviation_Cents', np.nan))]
                nan_notes = [n for n in dtw_metrics if np.isnan(n.get('Deviation_Cents', np.nan))]
                included = [n for n in detected if not is_note_excluded(n)]
                corr_applied = [n for n in detected if n.get('Correction_Applied', False)]
                over_100c = [n for n in detected if abs(n.get('Deviation_Cents', 0)) > 100 and not n.get('Correction_Applied', False)]

                det_yield = len(detected) / total_notes * 100 if total_notes > 0 else 0
                inc_yield = len(included) / total_notes * 100 if total_notes > 0 else 0
                mean_dev_hz = np.mean([n['Deviation_Hz'] for n in included]) if included else 0

                # NaN clustering analysis: split by quartile of note index
                q1 = total_notes // 4
                q2 = total_notes // 2
                q3 = 3 * total_notes // 4

                nan_indices = [n['Note_Index'] for n in nan_notes]
                nan_q1 = sum(1 for i in nan_indices if i <= q1)
                nan_q2 = sum(1 for i in nan_indices if q1 < i <= q2)
                nan_q3 = sum(1 for i in nan_indices if q2 < i <= q3)
                nan_q4 = sum(1 for i in nan_indices if i > q3)

                print(f"      Detected: {len(detected)}/{total_notes} ({det_yield:.2f}%)")
                print(f"      NaN: {len(nan_notes)} [Q1={nan_q1}, Q2={nan_q2}, Q3={nan_q3}, Q4={nan_q4}]")
                print(f"      Included: {len(included)}/{total_notes} ({inc_yield:.2f}%)")
                print(f"      Correction_Applied: {len(corr_applied)}, >100c: {len(over_100c)}")

                # Write CSV row
                with open(out_csv, 'a') as f:
                    f.write(f"{stem},{engine_name},{mode_name},{total_notes},"
                            f"{len(detected)},{det_yield:.2f},{len(nan_notes)},"
                            f"{len(included)},{inc_yield:.2f},{mean_dev_hz:.4f},"
                            f"{len(corr_applied)},{len(over_100c)},"
                            f"{nan_q1},{nan_q2},{nan_q3},{nan_q4}\n")

                # Full per-note diagnostics for primary target
                if is_full_diag:
                    diag_key = f"{stem}_{engine_name}_{mode_name}"
                    note_diags = []
                    for n in dtw_metrics:
                        dev_c = n.get('Deviation_Cents', float('nan'))
                        is_nan = np.isnan(dev_c)
                        note_diags.append({
                            "Note_Index": n.get("Note_Index"),
                            "Expected_Note": n.get("Expected_Note"),
                            "Deviation_Cents": round(dev_c, 2) if not is_nan else None,
                            "Deviation_Hz": round(n.get("Deviation_Hz", float('nan')), 2) if not is_nan else None,
                            "Is_NaN": is_nan,
                            "Correction_Applied": n.get("Correction_Applied", False),
                            "Correction_Type": n.get("Correction_Type", "None"),
                            "Excluded": is_note_excluded(n),
                        })
                    diagnostics[diag_key] = note_diags

            # Free memory between engines
            import gc
            del y, sr, f0, voiced_flag, rms, res, final_mask
            gc.collect()

    # Save diagnostics
    with open(out_json, 'w') as f:
        json.dump(diagnostics, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"Results saved to:")
    print(f"  CSV:  {out_csv}")
    print(f"  JSON: {out_json}")
    print(f"{'='*70}")

    # Print a quick summary comparison table
    print(f"\n{'='*70}")
    print("QUICK SUMMARY: Det_Yield by DTW mode")
    print(f"{'='*70}")
    print(f"{'Track':<30} {'Engine':<8} {'Global':>10} {'SubSeq':>10} {'Delta':>8}")
    print("-" * 70)

    import csv
    with open(out_csv, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Group by track+engine
    from collections import defaultdict
    grouped = defaultdict(dict)
    for r in rows:
        key = (r['Track'], r['Engine'])
        grouped[key][r['DTW_Mode']] = float(r['Det_Yield'])

    for (track, engine), modes in sorted(grouped.items()):
        g = modes.get('global', 0)
        s = modes.get('subsequence', 0)
        delta = s - g
        flag = " ***" if abs(delta) > 5 else ""
        print(f"{track:<30} {engine:<8} {g:>9.2f}% {s:>9.2f}% {delta:>+7.2f}%{flag}")


if __name__ == "__main__":
    main()

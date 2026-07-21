"""
test_k515_sigma2.py
-------------------
Focused test: runs all 5 K515 tracks (Vn1, Vn2, Va1, Va2, Vc) with both REAPER
and pYIN to measure the impact of the Müller Sigma_2 step pattern change.

Mirrors the exact run_appendix_a.py pipeline so results are directly comparable
against the Sigma_1 baseline stored in appendix_a_results.csv.
"""
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
import warnings
import gc
warnings.filterwarnings('ignore')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing, get_midi_tempo
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded


BASELINE = {
    "AuSep_1_vn_44_K515": {"Det_Yield_REAPER": 69.45, "Inc_Yield_REAPER": 54.98, "Dev_Hz_REAPER": 4.34,
                            "Det_Yield_pYIN": 98.39, "Inc_Yield_pYIN": 95.98, "Dev_Hz_pYIN": 6.84},
    "AuSep_2_vn_44_K515": {"Det_Yield_REAPER": 86.16, "Inc_Yield_REAPER": 67.30, "Dev_Hz_REAPER": 1.18,
                            "Det_Yield_pYIN": 91.82, "Inc_Yield_pYIN": 71.70, "Dev_Hz_pYIN": 0.75},
    "AuSep_3_va_44_K515": {"Det_Yield_REAPER": 93.71, "Inc_Yield_REAPER": 82.39, "Dev_Hz_REAPER": 0.36,
                            "Det_Yield_pYIN": 97.48, "Inc_Yield_pYIN": 92.87, "Dev_Hz_pYIN": 0.69},
    "AuSep_4_va_44_K515": {"Det_Yield_REAPER": 75.68, "Inc_Yield_REAPER": 63.81, "Dev_Hz_REAPER": 1.66,
                            "Det_Yield_pYIN": 81.71, "Inc_Yield_pYIN": 57.20, "Dev_Hz_pYIN": 1.56},
    "AuSep_5_vc_44_K515": {"Det_Yield_REAPER": 90.83, "Inc_Yield_REAPER": 73.61, "Dev_Hz_REAPER": 0.27,
                            "Det_Yield_pYIN": 93.61, "Inc_Yield_pYIN": 82.22, "Dev_Hz_pYIN": 0.51},
}

def main():
    print("=" * 70)
    print("K515 Sigma_2 Step Pattern Test")
    print("Step pattern: {(1,1),(2,1),(1,2)} with weights (2,1,1)")
    print("Comparing against Sigma_1 baseline from Appendix A")
    print("=" * 70)

    dataset_dir = Path(os.path.abspath(os.path.join(
        os.path.dirname(__file__), '../../../dataset (Strings only)/44_K515_vn_vn_va_va_vc')))

    if not dataset_dir.exists():
        print(f"Error: K515 dataset not found at {dataset_dir}")
        sys.exit(1)

    output_dir = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../outputs/batch_results')))
    output_dir.mkdir(exist_ok=True)
    out_csv = output_dir / "k515_sigma2_results.csv"

    engines = {
        "REAPER": {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 4, "switch_prob": 0.005},
        "pYIN":   {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 2, "switch_prob": 0.005}
    }

    toggles = {
        "freq_limits": True,
        "slope_filter": True,
        "duration_filter": True,
        "locked_target": True,
        "harmonic_folding": True,
        "force_global": True
    }

    track_dirs = sorted(dataset_dir.iterdir())
    results = []

    for track_dir in track_dirs:
        if not track_dir.is_dir():
            continue

        wav_files = list(track_dir.glob("AuSep_*.wav"))
        midi_files = list(track_dir.glob("*.mid"))
        if not wav_files or not midi_files:
            continue

        audio_path = wav_files[0]
        midi_path = midi_files[0]
        stem = audio_path.stem

        parts = stem.split('_')
        try:
            target_track = int(parts[1])
            inst_code = parts[2]
        except (IndexError, ValueError):
            continue

        inst_map = {"vn": "Violin", "va": "Viola", "vc": "Cello"}
        instrument_name = inst_map.get(inst_code, "Violin")

        print(f"\nProcessing: {stem} (Track: {target_track}, Inst: {instrument_name})")

        with open(str(midi_path), 'rb') as f:
            midi_notes = parse_midi_with_timing(f, target_track=target_track)
            if not midi_notes:
                f.seek(0)
                midi_notes = parse_midi_with_timing(f, target_track=0)
            if not midi_notes:
                f.seek(0)
                midi_notes = parse_midi_with_timing(f, target_track=1)

        if not midi_notes:
            print(f"  [!] No valid notes found")
            continue

        bpm = get_midi_tempo(str(midi_path))

        row_data = {
            "Filename": stem,
            "BPM": round(bpm, 1),
            "Instrument": instrument_name,
        }

        for engine, params in engines.items():
            print(f"  -> {engine}...", end=" ", flush=True)

            with open(str(audio_path), 'rb') as af:
                y, sr, f0, voiced_flag, rms, _ = extract_pitch_and_rms(
                    af,
                    instrument=instrument_name,
                    switch_prob=params['switch_prob'],
                    enable_freq_limits=toggles['freq_limits'],
                    pitch_engine=engine
                )

            res = analyze_intonation(
                y, sr, f0, voiced_flag, rms,
                rms_threshold=params['rms_threshold'],
                min_frames=params['min_frames'],
                max_pitch_slope=params['max_pitch_slope'],
                toggles=toggles
            )
            final_mask = res['final_mask']

            time_array, expected, warped, expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask, correction_array = process_dtw_alignment(
                midi_notes, f0, y, sr, final_mask, toggles, params['max_pitch_slope']
            )

            dtw_metrics = calculate_dtw_metrics(
                midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
            )

            if not dtw_metrics:
                row_data[f"Det_Yield_{engine}"] = 0.0
                row_data[f"Inc_Yield_{engine}"] = 0.0
                row_data[f"Dev_Hz_{engine}"] = 0.0
                print("no metrics")
                continue

            total_notes = len(dtw_metrics)
            valid_detected = [n for n in dtw_metrics if not np.isnan(n.get('Deviation_Cents', np.nan))]
            det_yield = len(valid_detected) / total_notes if total_notes > 0 else 0

            included = [n for n in valid_detected if not is_note_excluded(n)]
            inc_yield = len(included) / total_notes if total_notes > 0 else 0

            mean_dev_hz = np.mean([n['Deviation_Hz'] for n in included]) if included else 0

            row_data[f"Det_Yield_{engine}"] = round(det_yield * 100, 2)
            row_data[f"Inc_Yield_{engine}"] = round(inc_yield * 100, 2)
            row_data[f"Dev_Hz_{engine}"] = round(mean_dev_hz, 2)

            print(f"Det={det_yield*100:.1f}% Inc={inc_yield*100:.1f}% Dev={mean_dev_hz:.2f}Hz")

            del y, sr, f0, voiced_flag, rms, time_array, expected, warped
            del expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask
            del correction_array, dtw_metrics, valid_detected, included
            gc.collect()

        results.append(row_data)

    # Save results
    df = pd.DataFrame(results)
    df.to_csv(out_csv, index=False)

    # Print comparison table
    print("\n" + "=" * 120)
    print("COMPARISON: Sigma_1 (baseline) vs Sigma_2 (new)")
    print("=" * 120)
    print(f"{'Track':<25} | {'Engine':<7} | {'Det_Yield':>10} {'delta':>7} | {'Inc_Yield':>10} {'delta':>7} | {'Dev_Hz':>8} {'delta':>8}")
    print("-" * 120)

    for _, row in df.iterrows():
        stem = row['Filename']
        base = BASELINE.get(stem, {})
        for engine in ["REAPER", "pYIN"]:
            det_new = row.get(f"Det_Yield_{engine}", 0)
            inc_new = row.get(f"Inc_Yield_{engine}", 0)
            dev_new = row.get(f"Dev_Hz_{engine}", 0)

            det_old = base.get(f"Det_Yield_{engine}", 0)
            inc_old = base.get(f"Inc_Yield_{engine}", 0)
            dev_old = base.get(f"Dev_Hz_{engine}", 0)

            det_d = det_new - det_old
            inc_d = inc_new - inc_old
            dev_d = dev_new - dev_old

            det_arrow = "+" if det_d > 0 else ""
            inc_arrow = "+" if inc_d > 0 else ""
            dev_arrow = "+" if dev_d > 0 else ""

            print(f"{stem:<25} | {engine:<7} | {det_new:>9.2f}% {det_arrow}{det_d:>6.2f} | {inc_new:>9.2f}% {inc_arrow}{inc_d:>6.2f} | {dev_new:>7.2f} {dev_arrow}{dev_d:>7.2f}")

    print("=" * 120)
    print(f"Results saved to {out_csv}")


if __name__ == "__main__":
    main()

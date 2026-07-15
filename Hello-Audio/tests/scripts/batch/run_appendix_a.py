"""
run_appendix_a.py
-----------------
Batch test script for Appendix A: REAPER vs pYIN on the URMP string dataset.

Methodology:
- Mirrors the exact production pipeline (app.py): extract_pitch_and_rms →
  analyze_intonation (for final_mask) → process_dtw_alignment → calculate_dtw_metrics.
- Uses is_note_excluded() from midi_alignment.py as the single source of truth
  for note exclusion (abs(dev) > 100 cents OR Correction_Applied).
- Reports Mean Deviation in Hz to match the existing Appendix A table format.
- No duration cap: the original Appendix A was generated on full-length tracks.

File discovery:
- Only matches standard URMP AuSep_* naming convention.
- Skips AuMix_* polyphonic mix files and any other non-conforming filenames.
"""
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
import warnings
import librosa
import json
warnings.filterwarnings('ignore')

# Add root directory to sys path so we can import src modules
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing, get_midi_tempo
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded

# ============================================================
# Tracks to pull per-note Correction_Type diagnostics for
# (Item 3: tracks with large yield/deviation shifts)
# ============================================================
DIAGNOSTIC_TRACKS = [
    "AuSep_1_vn_12_Spring",
    "AuSep_1_vn_35_Rondeau",
    "AuSep_2_vc_11_Maria",
    "AuSep_1_vn_24_Pirates",
    "AuSep_1_vn_01_Jupiter",
]

def main():
    print("=" * 70)
    print("URMP Batch Test for Appendix A (REAPER vs pYIN)")
    print("Pipeline: extract → analyze_intonation → process_dtw_alignment")
    print("Exclusion: is_note_excluded() [abs(dev)>100c OR Correction_Applied]")
    print("No duration cap (full-length tracks)")
    print("=" * 70)
    
    dataset_dir = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '../dataset')))
    tests_dir = Path(os.path.abspath(os.path.dirname(__file__)))
    
    if not dataset_dir.exists():
        print(f"Error: Dataset directory not found at {dataset_dir}")
        sys.exit(1)
        
    # Output to a batch_results subdirectory inside tests/
    output_dir = tests_dir / "batch_results"
    output_dir.mkdir(exist_ok=True)
        
    out_csv = output_dir / "appendix_a_results.csv"
    diag_json = output_dir / "appendix_a_diagnostics.json"
    
    columns = [
        "Filename", "BPM", "Instrument", "Piece",
        "Det_Yield_REAPER", "Inc_Yield_REAPER", "Dev_Hz_REAPER",
        "Det_Yield_pYIN", "Inc_Yield_pYIN", "Dev_Hz_pYIN"
    ]
    pd.DataFrame(columns=columns).to_csv(out_csv, index=False)
    
    # Collect per-note diagnostics for flagged tracks
    diagnostics = {}
    
    # Recursively find all audio files matching the URMP AuSep_* convention ONLY
    audio_files = sorted(dataset_dir.rglob("AuSep_*.wav"))
    
    # Validate: log any non-AuSep wav files found (so we can confirm nothing else was swept in)
    all_wav = list(dataset_dir.rglob("*.wav"))
    non_ausep = [f for f in all_wav if not f.stem.startswith("AuSep_")]
    if non_ausep:
        print(f"\n[INFO] Skipping {len(non_ausep)} non-AuSep .wav files:")
        for f in non_ausep:
            print(f"  - {f.relative_to(dataset_dir)}")
    
    print(f"\n[INFO] Found {len(audio_files)} AuSep_*.wav tracks to process.\n")
    
    # Define Appendix A documented optimal parameters
    engines = {
        "REAPER": {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 4, "switch_prob": 0.005},
        "pYIN": {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 2, "switch_prob": 0.005}
    }
    
    # Fully explicit toggles dict based on Appendix A requirements
    toggles = {
        "freq_limits": True,
        "slope_filter": True,
        "duration_filter": True,
        "locked_target": True,
        "harmonic_folding": True,
        "force_global": True
    }
    
    for audio_path_obj in audio_files:
        audio_path = str(audio_path_obj)
        stem = audio_path_obj.stem
        
        # Skip polyphonic mix files
        if stem.startswith('AuMix'):
            continue
        
        # Look for a .mid file in the same directory
        parent_dir = audio_path_obj.parent
        midi_files = list(parent_dir.glob("*.mid"))
        if not midi_files:
            continue
            
        midi_path = str(midi_files[0])
        
        # Extract track index and instrument from filename
        # Standard URMP format: AuSep_{track}_{inst}_{piece_num}_{piece_name}
        parts = stem.split('_')
        try:
            target_track = int(parts[1])
            inst_code = parts[2]
        except (IndexError, ValueError):
            print(f"  [!] Skipping {stem}: cannot parse track/instrument from filename")
            continue
            
        inst_map = {
            "vn": "Violin", "va": "Viola", "vc": "Cello", "db": "Contrabass",
            "fl": "Flute", "ob": "Oboe", "cl": "Clarinet", "bn": "Bassoon",
            "sax": "Saxophone", "tpt": "Trumpet", "hn": "Horn", "tbn": "Trombone", "tba": "Tuba"
        }
        instrument_name = inst_map.get(inst_code, "Violin")
        
        # Exclude non-string instruments
        if instrument_name not in ["Violin", "Viola", "Cello"]:
            continue
            
        print(f"\nProcessing: {stem} (Track: {target_track}, Inst: {instrument_name})")
        
        # NO duration cap — process full track to match original Appendix A methodology
        with open(midi_path, 'rb') as f:
            midi_notes = parse_midi_with_timing(f, target_track=target_track)
            
        if not midi_notes:
            print(f"  [!] No valid notes found in Track {target_track}")
            continue
            
        bpm = get_midi_tempo(midi_path)
        
        row_data = {
            "Filename": stem,
            "BPM": round(bpm, 1),
            "Instrument": instrument_name,
            "Piece": parent_dir.name
        }
        
        is_diagnostic_track = stem in DIAGNOSTIC_TRACKS
        
        for engine, params in engines.items():
            print(f"  -> Testing {engine}...")
            
            with open(audio_path, 'rb') as af:
                y, sr, f0, voiced_flag, rms = extract_pitch_and_rms(
                    af, 
                    instrument=instrument_name,
                    switch_prob=params['switch_prob'],
                    enable_freq_limits=toggles['freq_limits'],
                    pitch_engine=engine
                    # No duration= parameter: process full track
                )
                
            # Generate final_mask by calling analyze_intonation exactly as app.py does.
            # This applies RMS threshold, slope filter, AND duration filter (min_frames).
            res = analyze_intonation(
                y, sr, f0, voiced_flag, rms, 
                rms_threshold=params['rms_threshold'], 
                min_frames=params['min_frames'], 
                max_pitch_slope=params['max_pitch_slope'], 
                toggles=toggles
            )
            final_mask = res['final_mask']
            
            # Process DTW alignment (exactly as app.py does)
            time_array, expected, warped, expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask, correction_array = process_dtw_alignment(
                midi_notes, f0, y, sr, final_mask, toggles, params['max_pitch_slope']
            )
            
            # Calculate metrics
            dtw_metrics = calculate_dtw_metrics(
                midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
            )
            
            if not dtw_metrics:
                row_data[f"Det_Yield_{engine}"] = 0.0
                row_data[f"Inc_Yield_{engine}"] = 0.0
                row_data[f"Dev_Hz_{engine}"] = 0.0
                continue
                
            total_notes = len(dtw_metrics)
            
            # Detected yield (standard tracking yield, ignoring exclusion logic)
            valid_detected_notes = [n for n in dtw_metrics if not np.isnan(n.get('Deviation_Cents', np.nan))]
            det_yield = len(valid_detected_notes) / total_notes if total_notes > 0 else 0
            
            # Included yield (after UI exclusion rule is applied via shared helper)
            included_notes = [n for n in valid_detected_notes if not is_note_excluded(n)]
            inc_yield = len(included_notes) / total_notes if total_notes > 0 else 0
            
            # Mean Deviation of Included notes (in Hz, to match original Appendix A format)
            mean_dev_hz = np.mean([n['Deviation_Hz'] for n in included_notes]) if included_notes else 0
            
            row_data[f"Det_Yield_{engine}"] = round(det_yield * 100, 2)
            row_data[f"Inc_Yield_{engine}"] = round(inc_yield * 100, 2)
            row_data[f"Dev_Hz_{engine}"] = round(mean_dev_hz, 2)
            
            # Collect per-note diagnostics for flagged tracks
            if is_diagnostic_track:
                diag_key = f"{stem}_{engine}"
                track_diag = []
                for n in dtw_metrics:
                    note_info = {
                        "Note_Index": n.get("Note_Index"),
                        "Expected_Note": n.get("Expected_Note"),
                        "Deviation_Cents": round(n.get("Deviation_Cents", float('nan')), 2) if not np.isnan(n.get("Deviation_Cents", float('nan'))) else None,
                        "Deviation_Hz": round(n.get("Deviation_Hz", float('nan')), 2) if not np.isnan(n.get("Deviation_Hz", float('nan'))) else None,
                        "Correction_Applied": n.get("Correction_Applied", False),
                        "Correction_Type": n.get("Correction_Type", "None"),
                        "Excluded": is_note_excluded(n),
                        "Exclusion_Reason": (
                            "Correction_Applied" if n.get("Correction_Applied", False)
                            else ">100_cents" if not np.isnan(n.get("Deviation_Cents", float('nan'))) and abs(n.get("Deviation_Cents", 0)) > 100
                            else "NaN/missed" if np.isnan(n.get("Deviation_Cents", float('nan')))
                            else "included"
                        )
                    }
                    track_diag.append(note_info)
                diagnostics[diag_key] = track_diag
            
            # Aggressive memory management
            import gc
            del y, sr, f0, voiced_flag, rms, time_array, expected, warped
            del expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask
            del correction_array, dtw_metrics, valid_detected_notes, included_notes
            gc.collect()
            
        # Append row safely
        pd.DataFrame([row_data]).to_csv(out_csv, mode='a', header=False, index=False)
        print(f"  [+] Data saved for {stem}")
        
    # Save diagnostics JSON
    with open(diag_json, 'w') as f:
        json.dump(diagnostics, f, indent=2, default=str)
    print(f"\n[+] Per-note diagnostics saved to {diag_json}")
    
    # Print summary of diagnostic tracks
    print("\n" + "=" * 70)
    print("DIAGNOSTIC TRACK SUMMARY")
    print("=" * 70)
    for key, notes in diagnostics.items():
        total = len(notes)
        excluded = sum(1 for n in notes if n["Excluded"])
        corr_applied = sum(1 for n in notes if n["Correction_Applied"])
        over_100c = sum(1 for n in notes if n["Exclusion_Reason"] == ">100_cents")
        missed = sum(1 for n in notes if n["Exclusion_Reason"] == "NaN/missed")
        
        print(f"\n{key}:")
        print(f"  Total notes: {total}")
        print(f"  Excluded: {excluded}  (Correction_Applied: {corr_applied}, >100c: {over_100c}, Missed/NaN: {missed})")
        
        # List the specific corrections
        corrections = [n for n in notes if n["Correction_Applied"]]
        if corrections:
            print(f"  Correction breakdown:")
            type_counts = {}
            for c in corrections:
                ct = c["Correction_Type"]
                type_counts[ct] = type_counts.get(ct, 0) + 1
            for ct, count in sorted(type_counts.items()):
                print(f"    {ct}: {count} notes")
    
    print(f"\n{'=' * 70}")
    print(f"Batch testing complete! Results saved to {out_csv}")
    print(f"{'=' * 70}")

if __name__ == "__main__":
    main()

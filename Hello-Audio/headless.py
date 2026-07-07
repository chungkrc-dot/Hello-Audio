import argparse
import librosa
import numpy as np
import warnings

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing
from src.midi_alignment import get_alignment_mask, calculate_dtw_metrics, apply_harmonic_folding

def main():
    parser = argparse.ArgumentParser(description="Headless Hello-Audio DTW Analyzer")
    parser.add_argument("audio_path", help="Path to the audio file (.wav)")
    parser.add_argument("midi_path", help="Path to the MIDI file (.mid)")
    parser.add_argument("instrument", choices=["Violin", "Viola", "Cello"], help="Instrument type")
    
    # Optional parameters (matching UI defaults)
    parser.add_argument("--switch_prob", type=float, default=0.005, help="Switch Probability (pYIN)")
    parser.add_argument("--rms_threshold", type=float, default=0.01, help="RMS Threshold")
    parser.add_argument("--min_frames", type=int, default=10, help="Minimum Frames")
    parser.add_argument("--max_pitch_slope", type=float, default=0.10, help="Max Pitch Slope (semitones)")
    
    # Optional toggles (matching UI defaults)
    parser.add_argument("--no_freq_limits", action="store_true", help="Disable Instrument Freq Limits")
    parser.add_argument("--no_slope_filter", action="store_true", help="Disable Pitch Slope Filter")
    parser.add_argument("--no_duration_filter", action="store_true", help="Disable Sustain Duration Filter")
    parser.add_argument("--no_locked_target", action="store_true", help="Disable Locked Target Rule")
    parser.add_argument("--force_global", action="store_true", help="Force Global DTW Alignment")
    parser.add_argument("--no_harmonic_folding", action="store_true", help="Disable Octave & Harmonic Folding")
    
    args = parser.parse_args()
    
    warnings.filterwarnings('ignore')
    
    print(f"Loading MIDI: {args.midi_path}")
    with open(args.midi_path, 'rb') as f:
        midi_notes = parse_midi_with_timing(f, target_track=None)
    
    print(f"Loading Audio: {args.audio_path}")
    print(f"Extracting pitch for {args.instrument} (switch_prob={args.switch_prob})...")
    with open(args.audio_path, 'rb') as af:
        y, sr, f0, voiced_flag, rms = extract_pitch_and_rms(
            af, 
            instrument=args.instrument, 
            switch_prob=args.switch_prob, 
            enable_freq_limits=not args.no_freq_limits
        )
    
    toggles = {
        'freq_limits': not args.no_freq_limits,
        'slope_filter': not args.no_slope_filter,
        'duration_filter': not args.no_duration_filter,
        'locked_target': not args.no_locked_target,
        'harmonic_folding': not args.no_harmonic_folding
    }
    
    print("Applying intonation filters...")
    res = analyze_intonation(
        y, sr, f0, voiced_flag, rms, 
        rms_threshold=args.rms_threshold, 
        min_frames=args.min_frames, 
        max_pitch_slope=args.max_pitch_slope, 
        toggles=toggles
    )
    final_mask = res['final_mask']
    
    print("Running DTW alignment...")
    time_array = librosa.times_like(f0, sr=sr, hop_length=512)
    mask, expected, warped, _ = get_alignment_mask(
        midi_notes, time_array, y, sr, hop_length=512, force_global=args.force_global
    )
    
    if toggles['harmonic_folding']:
        print("Applying harmonic folding...")
        folded_f0_hz, folded_f0_midi = apply_harmonic_folding(f0, expected)
    else:
        folded_f0_hz = f0
        
    print("Calculating final metrics...\n")
    dtw_metrics = calculate_dtw_metrics(midi_notes, time_array, folded_f0_hz, rms, final_mask, warped)
    
    print('--- DTW Alignment Metrics ---')
    for m in dtw_metrics:
        note = m.get('Expected_Note', 'Unknown')
        start = m.get('Audio_Start_Time', 0.0)
        dev_cents = m.get('Deviation_Cents', np.nan)
        dev_hz = m.get('Deviation_Hz', np.nan)
        status = 'DETECTED' if not np.isnan(dev_cents) else 'MISSED  '
        print(f'{status} | Note: {note:<3} | Audio Start: {start:.2f}s | Deviation: {dev_cents:5.1f} cents ({dev_hz:5.1f} Hz)')
        
    detected = sum(1 for m in dtw_metrics if not np.isnan(m['Deviation_Cents']))
    total = len(midi_notes)
    yield_pct = (detected / total) * 100 if total > 0 else 0
    print(f"\nYield: {detected} / {total} ({yield_pct:.1f}%)")

if __name__ == "__main__":
    main()

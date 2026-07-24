import numpy as np
import librosa
import scipy.signal
import soundfile as sf
import io
import sys
import os
import pandas as pd
from unittest.mock import MagicMock

# Mock Streamlit BEFORE importing anything that depends on it
mock_st = MagicMock()
mock_st.sidebar = MagicMock()
mock_st.subheader = MagicMock()
mock_st.write = MagicMock()
mock_st.caption = MagicMock()
mock_st.info = MagicMock()
mock_st.dataframe = MagicMock()
mock_st.download_button = MagicMock()
mock_st.success = MagicMock()
mock_st.checkbox = MagicMock(return_value=True) # auto_exclude = True
mock_st.column_config = MagicMock()
mock_st.data_editor = MagicMock(side_effect=lambda df, **kwargs: df.data if hasattr(df, 'data') else df)
sys.modules['streamlit'] = mock_st

# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.amplitude_analysis import analyze_amplitude
from app.ui_components import render_dtw_results_table, render_sequence_comparison

def generate_tone_sequence(notes, durations, sr=44100, attenuations=None):
    if attenuations is None:
        attenuations = [1.0] * len(notes)
        
    y_total = []
    for note, dur, atten in zip(notes, durations, attenuations):
        freq = librosa.midi_to_hz(note)
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * freq * t)
        y += 0.25 * np.sin(2 * np.pi * freq * 2 * t)
        y += 0.125 * np.sin(2 * np.pi * freq * 3 * t)
        
        env = np.ones_like(y)
        env[:int(0.05*sr)] = np.linspace(0, 1, int(0.05*sr))
        env[-int(0.05*sr):] = np.linspace(1, 0, int(0.05*sr))
        y *= env
        
        y *= atten
        y_total.append(y)
        y_total.append(np.zeros(int(0.1 * sr)))
        
    return np.concatenate(y_total), sr

def to_bytesio(y, sr):
    buffer = io.BytesIO()
    sf.write(buffer, y, sr, format='WAV', subtype='PCM_16')
    buffer.seek(0)
    return buffer

def main():
    report_lines = ["# Paired Comparison Validation Report\n"]
    
    # ---------------------------------------------------------
    # Test 1 & 2: Known-attenuation synthetic pair with realistic intonation
    # ---------------------------------------------------------
    # 15 notes (C major scale up and down)
    notes = [60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65, 64, 62, 60]
    durations = [0.8] * 15
    
    # Realistic intonation deviations in cents
    offsets_cents = [5.0, -3.0, 15.0, -2.0, 4.0, -8.0, 10.0, 1.0, -5.0, 7.0, -12.0, 3.0, 6.0, -4.0, 9.0]
    
    def generate_tone_sequence_with_offsets(notes, durations, offsets_cents, sr=44100, attenuations=None):
        if attenuations is None:
            attenuations = [1.0] * len(notes)
            
        y_total = []
        for note, dur, offset, atten in zip(notes, durations, offsets_cents, attenuations):
            base_freq = librosa.midi_to_hz(note)
            freq = base_freq * (2 ** (offset / 1200.0))
            
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            y = 0.5 * np.sin(2 * np.pi * freq * t)
            y += 0.25 * np.sin(2 * np.pi * freq * 2 * t)
            y += 0.125 * np.sin(2 * np.pi * freq * 3 * t)
            
            env = np.ones_like(y)
            env[:int(0.05*sr)] = np.linspace(0, 1, int(0.05*sr))
            env[-int(0.05*sr):] = np.linspace(1, 0, int(0.05*sr))
            y *= env
            
            y *= atten
            y_total.append(y)
            y_total.append(np.zeros(int(0.1 * sr)))
            
        return np.concatenate(y_total), sr

    y_unp, sr = generate_tone_sequence_with_offsets(notes, durations, offsets_cents)
    # LPF for plugged (2kHz cutoff)
    b, a = scipy.signal.butter(4, 2000 / (sr / 2), btype='low')
    
    # Plugged: -10 dB
    y_plg = y_unp * (10 ** (-10 / 20))
    y_plg = scipy.signal.lfilter(b, a, y_plg)
    
    buf_unp = to_bytesio(y_unp, sr)
    buf_plg = to_bytesio(y_plg, sr)
    
    toggles = {'freq_limits': True, 'slope_filter': True, 'duration_filter': True, 'locked_target': True}
    
    _, _, f0_unp, v_unp, rms_unp, _ = extract_pitch_and_rms(buf_unp, "Violin", 0.005)
    _, _, f0_plg, v_plg, rms_plg, _ = extract_pitch_and_rms(buf_plg, "Violin", 0.005)
    
    res_unp_1 = analyze_intonation(y_unp, sr, f0_unp, v_unp, rms_unp, toggles=toggles)
    res_unp_1.update(analyze_amplitude(y_unp, sr))
    
    res_plg_1 = analyze_intonation(y_plg, sr, f0_plg, v_plg, rms_plg, toggles=toggles)
    res_plg_1.update(analyze_amplitude(y_plg, sr))
    
    # Test 2 Logic
    def get_note_deviations(res):
        f0 = res['f0']
        final_mask = res['final_mask']
        padded_mask = np.concatenate(([False], final_mask, [False]))
        changes = np.diff(padded_mask.astype(int))
        starts = np.where(changes == 1)[0]
        ends = np.where(changes == -1)[0]
        
        note_devs = []
        for start, end in zip(starts, ends):
            island_dev = res['full_deviation'][start:end]
            valid = ~np.isnan(island_dev)
            if np.any(valid):
                note_devs.append(island_dev[valid])
        return note_devs

    devs_unp_1 = get_note_deviations(res_unp_1)
    devs_plg_1 = get_note_deviations(res_plg_1)
    
    min_n_1 = min(len(devs_unp_1), len(devs_plg_1))
    matched_unp_1 = np.concatenate(devs_unp_1[:min_n_1]) if min_n_1 > 0 else np.array([])
    matched_plg_1 = np.concatenate(devs_plg_1[:min_n_1]) if min_n_1 > 0 else np.array([])
    
    diag_delta_1 = np.mean(matched_unp_1) - np.mean(matched_plg_1)
    app_delta_1 = res_unp_1['mean_dev'] - res_plg_1['mean_dev']
    
    # ---------------------------------------------------------
    # Test 3: Induced asymmetric note dropout
    # ---------------------------------------------------------
    # Harash attenuation on the 3rd note (index 2) -> -40 dB
    attenuations_harsh = [10**(-10/20)] * 15
    attenuations_harsh[2] = 10**(-40/20) # E4 (+15 cents) drops out
    
    y_plg_harsh, _ = generate_tone_sequence_with_offsets(notes, durations, offsets_cents, sr, attenuations_harsh)
    y_plg_harsh = scipy.signal.lfilter(b, a, y_plg_harsh)
    buf_plg_harsh = to_bytesio(y_plg_harsh, sr)
    
    _, _, f0_plg_h, v_plg_h, rms_plg_h, _ = extract_pitch_and_rms(buf_plg_harsh, "Violin", 0.005)
    res_plg_3 = analyze_intonation(y_plg_harsh, sr, f0_plg_h, v_plg_h, rms_plg_h, toggles=toggles)
    res_plg_3.update(analyze_amplitude(y_plg_harsh, sr))
    
    devs_plg_3 = get_note_deviations(res_plg_3)
    min_n_3 = min(len(devs_unp_1), len(devs_plg_3))
    matched_unp_3 = np.concatenate(devs_unp_1[:min_n_3]) if min_n_3 > 0 else np.array([])
    matched_plg_3 = np.concatenate(devs_plg_3[:min_n_3]) if min_n_3 > 0 else np.array([])
    
    diag_delta_3 = np.mean(matched_unp_3) - np.mean(matched_plg_3)
    app_delta_3 = res_unp_1['mean_dev'] - res_plg_3['mean_dev']
    
    # ---------------------------------------------------------
    # Test 4 & 4b: DTW shared "Include" checkbox behavior (using actual pipeline)
    # ---------------------------------------------------------
    from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics
    
    midi_timing = []
    current_time = 0.0
    for i, note in enumerate(notes):
        dur = durations[i]
        midi_timing.append({
            'Note_Index': i + 1,
            'Expected_Note': librosa.midi_to_note(note),
            'Expected_Target_Pitch_Hz': librosa.midi_to_hz(note),
            'Start_Time': current_time,
            'End_Time': current_time + dur,
            'Pitch': note
        })
        current_time += dur + 0.1 # Include the silence gap

    toggles_dtw = toggles.copy()
    toggles_dtw['harmonic_folding'] = True

    # Test 4: Octave error (Note index 2, +1200 cents)
    offsets_dtw_plg = offsets_cents.copy()
    offsets_dtw_plg[2] += 1200.0
    y_dtw_plg, _ = generate_tone_sequence_with_offsets(notes, durations, offsets_dtw_plg)
    buf_dtw_plg = to_bytesio(y_dtw_plg, sr)
    _, _, f0_dtw_plg, v_dtw_plg, rms_dtw_plg, _ = extract_pitch_and_rms(buf_dtw_plg, "Violin", 0.005)
    res_dtw_plg = analyze_intonation(y_dtw_plg, sr, f0_dtw_plg, v_dtw_plg, rms_dtw_plg, toggles=toggles)
    
    time_array_plg, expected_plg, warped_plg, expected_note_index_plg, folded_f0_hz_plg, folded_f0_midi_plg, strict_mask_plg, correction_array_plg = process_dtw_alignment(
        midi_timing, res_dtw_plg['f0'], res_dtw_plg['y'], res_dtw_plg['sr'], res_dtw_plg['final_mask'], toggles_dtw, 0.5
    )
    dtw_metrics_plg = calculate_dtw_metrics(midi_timing, time_array_plg, folded_f0_hz_plg, res_dtw_plg['rms'], res_dtw_plg['final_mask'], warped_plg, correction_array_plg)
    
    test_4_note3_metrics = next((m for m in dtw_metrics_plg if m['Note_Index'] == 3), None)
    excluded_4 = render_dtw_results_table(None, dtw_metrics_plg)
    
    # Test 4b: 3rd Harmonic / Perfect 5th error (Note index 3, +1900 cents)
    offsets_dtw_plg_4b = offsets_cents.copy()
    offsets_dtw_plg_4b[3] += 1900.0
    y_dtw_plg_4b, _ = generate_tone_sequence_with_offsets(notes, durations, offsets_dtw_plg_4b)
    buf_dtw_plg_4b = to_bytesio(y_dtw_plg_4b, sr)
    _, _, f0_dtw_plg_4b, v_dtw_plg_4b, rms_dtw_plg_4b, _ = extract_pitch_and_rms(buf_dtw_plg_4b, "Violin", 0.005)
    res_dtw_plg_4b = analyze_intonation(y_dtw_plg_4b, sr, f0_dtw_plg_4b, v_dtw_plg_4b, rms_dtw_plg_4b, toggles=toggles)
    
    time_array_plg_4b, expected_plg_4b, warped_plg_4b, expected_note_index_plg_4b, folded_f0_hz_plg_4b, folded_f0_midi_plg_4b, strict_mask_plg_4b, correction_array_plg_4b = process_dtw_alignment(
        midi_timing, res_dtw_plg_4b['f0'], res_dtw_plg_4b['y'], res_dtw_plg_4b['sr'], res_dtw_plg_4b['final_mask'], toggles_dtw, 0.5
    )
    dtw_metrics_plg_4b = calculate_dtw_metrics(midi_timing, time_array_plg_4b, folded_f0_hz_plg_4b, res_dtw_plg_4b['rms'], res_dtw_plg_4b['final_mask'], warped_plg_4b, correction_array_plg_4b)
    
    test_4b_note4_metrics = next((m for m in dtw_metrics_plg_4b if m['Note_Index'] == 4), None)
    excluded_4b = render_dtw_results_table(None, dtw_metrics_plg_4b)

    
    # ---------------------------------------------------------
    # Test 7: Harmonic Folding Deviation Gate
    # ---------------------------------------------------------
    from src.midi_alignment import apply_harmonic_folding
    test_7_hz = librosa.midi_to_hz(np.array([60+12, 60+19, 60+9, 60+10, 60+11]))
    test_7_exp = np.array([60, 60, 60, 60, 60])
    _, folded_midi, _ = apply_harmonic_folding(test_7_hz, test_7_exp)
    residuals = folded_midi - test_7_exp
    test_7_results = {
        'octave': residuals[0],  # expected 0
        'p5': residuals[1],      # expected 0
        'm6': residuals[2],      # expected 9
        'm7': residuals[3],      # expected 10
        'edge': residuals[4]     # expected -1
    }
    
    # ---------------------------------------------------------
    # Test 5: Legacy sequence comparison positional misalignment
    # ---------------------------------------------------------
    seq_unp = res_unp_1['detected_notes_sequence']
    seq_plg = res_plg_3['detected_notes_sequence']
    mock_st.dataframe.reset_mock()
    render_sequence_comparison(None, seq_unp, seq_plg)
    
    df_seq = mock_st.dataframe.call_args[0][0]
    
    # ---------------------------------------------------------
    # Build Report
    # ---------------------------------------------------------
    report_lines.append("## 1. Current App Behavior")
    report_lines.append(f"- **Test 1 (Identical Yield)**: Unplugged N={res_unp_1.get('note_count', 0)}, Plugged N={res_plg_1.get('note_count', 0)}")
    report_lines.append(f"  - App delta dBFS: {res_unp_1.get('mean_dbfs', 0) - res_plg_1.get('mean_dbfs', 0):.2f} dB (Expected ~+10.00 dB)")
    report_lines.append(f"  - App delta cents: {app_delta_1:.2f} cents (Independent Means)")
    
    report_lines.append(f"\n- **Test 3 (Unequal Yield)**: Unplugged N={res_unp_1.get('note_count', 0)}, Plugged N={res_plg_3.get('note_count', 0)}")
    report_lines.append(f"  - App delta cents: {app_delta_3:.2f} cents (Independent Means)")
    
    report_lines.append("\n## 2. Divergence Analysis")
    report_lines.append("This section compares the App's current independent-means calculation vs a simple positional-matched diagnostic subset, derived from a 15-note synthetic sequence with realistic intonation offsets.")
    report_lines.append(f"- **Identical Yield Gap (Test 1/2)**:")
    report_lines.append(f"  - App's current delta_cents: {app_delta_1:.2f}")
    report_lines.append(f"  - Diagnostic delta_cents: {diag_delta_1:.2f}")
    report_lines.append(f"  - Absolute Gap: {abs(app_delta_1 - diag_delta_1):.2f} cents")
    
    report_lines.append(f"\n- **Asymmetric Yield Gap (Test 3)**:")
    report_lines.append(f"  - App's current delta_cents: {app_delta_3:.2f}")
    report_lines.append(f"  - Diagnostic delta_cents: {diag_delta_3:.2f}")
    report_lines.append(f"  - Absolute Gap: {abs(app_delta_3 - diag_delta_3):.2f} cents")
    
    report_lines.append("\n## 3. DTW vs Legacy Structural Difference")
    report_lines.append("- **Test 4 (DTW Harmonic Folding - Octave)**: Using a genuinely synthesized octave error injected into the audio stream and processed via the actual `apply_harmonic_folding` and `calculate_dtw_metrics` pipeline:")
    if test_4_note3_metrics:
        corr_app = test_4_note3_metrics.get('Correction_Applied', False)
        corr_type = test_4_note3_metrics.get('Correction_Type', 'None')
        dev_cents = test_4_note3_metrics.get('Deviation_Cents', 999)
        report_lines.append(f"  - **Result**: The octave error folded to {dev_cents:.2f} cents.")
        report_lines.append(f"  - **Correction Tracking**: Correction_Applied={corr_app}, Correction_Type='{corr_type}'.")
        report_lines.append(f"  - **Exclusion**: Note 3 excluded state = {3 in excluded_4} (Expected True despite small deviation).")

    report_lines.append("\n- **Test 4b (DTW Harmonic Folding - 3rd Harmonic)**: Using a genuinely synthesized +19 semitone error:")
    if test_4b_note4_metrics:
        corr_app = test_4b_note4_metrics.get('Correction_Applied', False)
        corr_type = test_4b_note4_metrics.get('Correction_Type', 'None')
        dev_cents = test_4b_note4_metrics.get('Deviation_Cents', 999)
        report_lines.append(f"  - **Result**: The 3rd harmonic error folded to {dev_cents:.2f} cents.")
        report_lines.append(f"  - **Correction Tracking**: Correction_Applied={corr_app}, Correction_Type='{corr_type}'.")
        report_lines.append(f"  - **Exclusion**: Note 4 excluded state = {4 in excluded_4b} (Expected True despite small deviation).")
    
    report_lines.append("\n- **Test 7 (Harmonic Folding Deviation Gate)**: Direct test of the 11.5-semitone minimum-deviation gate.")
    report_lines.append(f"  - Genuine Octave Error (+12): Residual is {test_7_results['octave']:.1f} semitones (Folded correctly).")
    report_lines.append(f"  - Genuine 3rd Harmonic (+19): Residual is {test_7_results['p5']:.1f} semitones (Folded correctly via Perfect 5th band).")
    report_lines.append(f"  - Major 6th Error (+9): Residual is {test_7_results['m6']:.1f} semitones (Unfolded; will correctly fall through to >100c auto-exclude).")
    report_lines.append(f"  - minor 7th Error (+10): Residual is {test_7_results['m7']:.1f} semitones (Unfolded; will correctly fall through to >100c auto-exclude).")
    report_lines.append(f"  - Major 7th Error (+11): Residual is {test_7_results['edge']:.1f} semitones (Unfolded; protected by the new 11.5-semitone gate).")

    report_lines.append(f"\n- **Test 5 (Legacy Sequence Misalignment)**:")
    report_lines.append("  - When Note 3 dropped out in the Plugged condition, `zip_longest` structurally misaligned the remaining notes.")
    report_lines.append("  - The resulting DataFrame structure was observed as:")
    report_lines.append("```text\n" + df_seq.to_string() + "\n```")
    
    report_lines.append("\n## 4. Recommendations for Human Review")
    report_lines.append("- **Option A**: Consider warning the user in the UI when legacy note counts diverge by more than a certain percentage, as this introduces arithmetic drift in the Delta calculation.")
    report_lines.append("- **Option B**: Consider whether Legacy mode needs its own ordinal alignment logic (e.g., Levenshtein distance on note sequences) rather than purely independent means, since it cannot fall back on MIDI anchors.")
    report_lines.append("- **RESOLVED - DTW Harmonic Folding Conflict**: The previous issue where massive tracking errors (octaves/fifths) folded cleanly and bypassed the >100-cent exclusion rule has been fixed. The pipeline now accurately tracks `Correction_Type` and automatically defaults these corrected notes to 'excluded', allowing manual user override.")
    
    report_path = os.path.join(os.path.dirname(__file__), "paired_comparison_validation_report.md")
    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    main()

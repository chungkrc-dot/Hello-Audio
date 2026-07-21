"""
midi_alignment.py
-----------------
The core mathematical engine for aligning audio to a MIDI reference using Dynamic Time Warping (DTW).
This module handles synthesizing reference audio, performing DTW alignment, calculating octave-agnostic 
pitch boundaries, and extracting precise intonation metrics bound strictly to the MIDI temporal expectations.
"""
import numpy as np

def is_note_excluded(note_dict):
    """
    Centralized logic for determining if a note should be excluded from summary metrics.
    Excludes gross tracking errors (>100 cents) and notes where harmonic folding was applied.
    """
    dev_cents = note_dict.get("Deviation_Cents", float('nan'))
    corr_applied = note_dict.get("Correction_Applied", False)
    
    if np.isnan(dev_cents):
        return True # Missing note
        
    if abs(dev_cents) > 100 or corr_applied:
        return True
        
    return False

def get_midi_chroma(midi_notes, sr, hop_length):
    """
    Synthesizes a basic sine-wave audio track from the MIDI score and extracts 12-bin Chroma CQT.
    """
    import numpy as np
    import librosa
    
    if not midi_notes:
        return np.array([])
        
    # We force first_start to 0 so that the synthesized MIDI track preserves leading rests/silence.
    # Otherwise, DTW maps the audio's leading silence to the first MIDI note!
    first_start = 0
    last_end = midi_notes[-1]['End_Time'] if isinstance(midi_notes[-1], dict) else getattr(midi_notes[-1], 'End_Time', 0)
    
    duration = last_end - first_start
    total_samples = int(np.ceil(duration * sr))
    y_midi = np.zeros(total_samples)
    
    t = np.arange(total_samples) / sr
    
    for note in midi_notes:
        start_time = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
        end_time = note['End_Time'] if isinstance(note, dict) else getattr(note, 'End_Time', 0)
        pitch = note['Pitch'] if isinstance(note, dict) else getattr(note, 'Pitch', np.nan)
        
        if np.isnan(pitch):
            continue
            
        freq = librosa.midi_to_hz(pitch)
        
        local_start = start_time - first_start
        local_end = end_time - first_start
        
        start_sample = int(np.floor(local_start * sr))
        end_sample = int(np.ceil(local_end * sr))
        
        start_sample = max(0, start_sample)
        end_sample = min(total_samples, end_sample)
        
        if start_sample < end_sample:
            note_t = t[start_sample:end_sample] - local_start
            wave = np.sin(2 * np.pi * freq * note_t)
            y_midi[start_sample:end_sample] += wave
            
    chroma = librosa.feature.chroma_cqt(y=y_midi, sr=sr, hop_length=hop_length, fmin=65.4)
    chroma = np.nan_to_num(chroma, nan=0.0)
    return chroma + 1e-6

def get_audio_chroma(audio_y, sr, hop_length):
    """
    Extracts the 12-bin Chroma CQT from the raw audio waveform.
    """
    import numpy as np
    import librosa
    chroma = librosa.feature.chroma_cqt(y=audio_y, sr=sr, hop_length=hop_length, fmin=65.4)
    chroma = np.nan_to_num(chroma, nan=0.0)
    return chroma + 1e-6

def compute_dtw_path(midi_chroma, audio_chroma, force_global=False):
    """
    Computes the Dynamic Time Warping (DTW) path between MIDI and Audio Chroma.
    Automatically handles sequence length swapping to satisfy librosa's subseq requirements,
    unless force_global=True which forces a global alignment.

    Uses Müller's Sigma_2 step pattern {(1,1),(2,1),(1,2)} with weights (2,1,1)
    to prevent degenerate warping paths.
    """
    import numpy as np
    import librosa

    # Müller (2015) Sigma_2: eliminates pure horizontal/vertical steps,
    # constraining the warping path slope to [1/2, 2].
    step_sizes_sigma = np.array([[1, 1], [2, 1], [1, 2]], dtype=np.uint32)
    weights_mul = np.array([2.0, 1.0, 1.0], dtype=np.float64)

    # Subsequence DTW requires the shorter query sequence to be the first argument (X)
    # and the longer reference sequence to be the second argument (Y).
    # We dynamically swap them so the algorithm is mathematically robust to any tempo.

    len_midi = midi_chroma.shape[1]
    len_audio = audio_chroma.shape[1]

    if force_global:
        # Force global alignment, anchoring the start and end of both sequences.
        D, wp = librosa.sequence.dtw(
            midi_chroma,
            audio_chroma,
            metric='cosine',
            step_sizes_sigma=step_sizes_sigma,
            weights_mul=weights_mul,
            subseq=False
        )
        wp = np.fliplr(wp)
    elif len_midi <= len_audio:
        # MIDI is shorter (student played slow). Normal configuration.
        D, wp = librosa.sequence.dtw(
            midi_chroma,
            audio_chroma,
            metric='cosine',
            step_sizes_sigma=step_sizes_sigma,
            weights_mul=weights_mul,
            subseq=True
        )
        # wp has shape (N, 2), where column 0 = MIDI, column 1 = Audio.
        # Downstream expects (Audio, MIDI), so we flip it.
        wp = np.fliplr(wp)
    else:
        # Audio is shorter (student played fast). Swapped configuration.
        D, wp = librosa.sequence.dtw(
            audio_chroma,
            midi_chroma,
            metric='cosine',
            step_sizes_sigma=step_sizes_sigma,
            weights_mul=weights_mul,
            subseq=True
        )
        # wp has shape (N, 2), where column 0 = Audio, column 1 = MIDI.
        # This is already the downstream expected format (Audio, MIDI), so no flip is needed!
        pass

    return wp


def get_alignment_mask(midi_notes, time_array, audio_y, sr, hop_length=512, force_global=False):
    """
    Main orchestration function for DTW alignment. 
    1. Synthesizes a reference audio track from the MIDI sequence.
    2. Runs DTW between the real audio and synthetic MIDI audio using Chroma CQT features.
    3. Back-projects the MIDI temporal boundaries onto the real audio timeline.
    4. Generates an inclusion mask that perfectly aligns with the expected notes.
    """
    import numpy as np
    import librosa
    
    # 1. Generate multi-dimensional Chroma features for robust DTW
    midi_chroma = get_midi_chroma(midi_notes, sr, hop_length)
    audio_chroma = get_audio_chroma(audio_y, sr, hop_length)
    
    # 2. Compute DTW on Chroma
    # wp is formatted as [audio_frame, midi_frame]
    wp = compute_dtw_path(midi_chroma, audio_chroma, force_global=force_global)
    
    # 3. Convert DTW path to absolute time mapping
    # Since we set first_start to 0 in get_midi_chroma, the MIDI times are already absolute!
    first_start = 0
    audio_times = librosa.frames_to_time(wp[:, 0], sr=sr, hop_length=hop_length)
    midi_times = librosa.frames_to_time(wp[:, 1], sr=sr, hop_length=hop_length) + first_start
    
    # Ensure audio_times is strictly increasing for np.interp by picking unique audio frames
    unique_audio_times, unique_indices = np.unique(audio_times, return_index=True)
    unique_midi_times = midi_times[unique_indices]
    
    # 4. Interpolate to find exactly where every audio frame lands on the MIDI timeline
    warped_midi_timeline = np.interp(time_array, unique_audio_times, unique_midi_times)
    
    # 5. Build the mask and the expected audio pitch array natively on the audio timeline
    valid_dtw_mask = np.zeros(len(time_array), dtype=bool)
    expected_audio_pitch = np.full(len(time_array), np.nan)
    expected_note_index = np.full(len(time_array), "", dtype=object)
    
    for i, note in enumerate(midi_notes):
        start_time = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
        end_time = note['End_Time'] if isinstance(note, dict) else getattr(note, 'End_Time', 0)
        pitch = note['Pitch'] if isinstance(note, dict) else getattr(note, 'Pitch', np.nan)
        
        # Find which audio frames' warped timeline falls within this note's duration
        note_mask = (warped_midi_timeline >= start_time) & (warped_midi_timeline < end_time)
        
        valid_dtw_mask[note_mask] = True
        expected_audio_pitch[note_mask] = pitch
        expected_note_index[note_mask] = f"Note {i+1}"
        
    return valid_dtw_mask, expected_audio_pitch, warped_midi_timeline, expected_note_index

def apply_harmonic_folding(f0_hz, expected_midi_pitch):
    """
    Algorithm to mathematically fold the raw extracted pitch (f0) into the target pitch.
    This corrects algorithmic "octave errors" and harmonic confusion (e.g. tracking a Perfect 5th 
    instead of the fundamental) inherent in pYIN when tracking rich acoustic instruments.
    """
    import numpy as np
    import librosa
    
    f0_midi = librosa.hz_to_midi(f0_hz)
    valid_mask = ~np.isnan(f0_midi) & ~np.isnan(expected_midi_pitch)
    
    # 1. Calculate raw deviation
    raw_dev = np.zeros_like(f0_midi)
    raw_dev[valid_mask] = f0_midi[valid_mask] - expected_midi_pitch[valid_mask]
    
    # Gate: only fold if absolute raw deviation >= 11.5 semitones
    # This protects genuine performance errors (e.g., misplaying a 6th or 7th) from being masked as harmonic artifacts
    fold_gate = valid_mask & (np.abs(raw_dev) >= 11.5)
    
    # Start with f0_midi_oct as the unfolded f0_midi
    f0_midi_oct = np.copy(f0_midi)
    
    # 2. Octave Folding (only for those that pass the gate)
    octave_offsets = np.zeros_like(f0_midi)
    octave_offsets[fold_gate] = np.round(raw_dev[fold_gate] / 12.0)
    
    f0_midi_oct[fold_gate] = f0_midi[fold_gate] - (octave_offsets[fold_gate] * 12.0)
    
    # 3. Harmonic Folding (only for those that pass the gate)
    # Recompute residual deviation after octave folding
    dev = np.zeros_like(f0_midi)
    dev[fold_gate] = f0_midi_oct[fold_gate] - expected_midi_pitch[fold_gate]
    
    # Perfect 5th confusion (e.g. 3rd, 6th harmonics) mathematically folds to around -5.0
    is_fifth_harmonic = fold_gate & (dev >= -5.5) & (dev <= -4.5)
    f0_midi_oct[is_fifth_harmonic] += 5.0
    
    # Major 3rd confusion (e.g. 5th harmonic) mathematically folds to around +4.0
    is_third_harmonic = fold_gate & (dev >= 3.5) & (dev <= 4.5)
    f0_midi_oct[is_third_harmonic] -= 4.0
    
    folded_f0_hz = librosa.midi_to_hz(f0_midi_oct)
    
    correction_array = np.full(len(f0_midi), "None", dtype=object)
    for i in range(len(f0_midi)):
        if not fold_gate[i]:
            continue
            
        oct_val = int(np.abs(octave_offsets[i]))
        is_5th = is_fifth_harmonic[i]
        is_3rd = is_third_harmonic[i]
        
        if oct_val == 0 and not is_5th and not is_3rd:
            continue
            
        parts = []
        if oct_val > 0:
            parts.append(f"Octave (x{oct_val})" if oct_val > 1 else "Octave")
        
        if is_5th:
            parts.append("Perfect 5th")
        elif is_3rd:
            parts.append("Major 3rd")
            
        correction_array[i] = " + ".join(parts)
    
    return folded_f0_hz, f0_midi_oct, correction_array

def calculate_dtw_metrics(midi_notes, time_array, f0, rms, final_mask, warped_midi_timeline, correction_array=None, voicing_prob=None, reference_pitch_hz=440.0):
    """
    Extracts the final intonation and amplitude metrics for every note in the sequence.
    It isolates the exact temporal island of the note using the DTW warped timeline, 
    applies the strict pYIN/slope masks, and computes the mathematically robust Median 
    to filter out transient attacks and glissandos.
    """
    import numpy as np
    import librosa
    
    dtw_results = []
    
    # We loop through the exact sequence of true MIDI notes
    for i, note in enumerate(midi_notes):
        start_time = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
        end_time = note['End_Time'] if isinstance(note, dict) else getattr(note, 'End_Time', 0)
        pitch = note['Pitch'] if isinstance(note, dict) else getattr(note, 'Pitch', np.nan)
        note_name = librosa.midi_to_note(pitch) if not np.isnan(pitch) else "Rest"
        
        # Isolate the audio frames warped to this exact note's time boundary
        note_mask = (warped_midi_timeline >= start_time) & (warped_midi_timeline < end_time)
        
        # Apply the legacy final_mask to strictly filter out transients and slides
        strict_note_mask = note_mask & final_mask
        
        if np.any(strict_note_mask):
            # Extract values
            note_f0 = f0[strict_note_mask]
            note_rms = rms[strict_note_mask]
            
            # Median f0 inside this strict, folded island
            median_f0 = np.nanmedian(note_f0)
            median_midi = librosa.hz_to_midi(median_f0)
            tuning_offset = 1200 * np.log2(reference_pitch_hz / 440.0) / 100.0
            median_midi_corrected = median_midi - tuning_offset

            # Deviation from the TRUE MIDI pitch (cents)
            deviation_cents = (median_midi_corrected - pitch) * 100
            
            # Convert deviation to Hz — shift expected frequency by tuning ratio
            expected_hz = librosa.midi_to_hz(pitch) * (reference_pitch_hz / 440.0)
            deviation_hz = median_f0 - expected_hz
            
            # RMS in dBFS
            median_rms_dbfs = 20 * np.log10(np.nanmedian(note_rms) + 1e-10)
            
            # RMS in dBA
            median_rms_dba = median_rms_dbfs + librosa.A_weighting(median_f0)
            
            # Correction logic
            correction_applied = False
            correction_type = "None"
            if correction_array is not None:
                note_corrections = correction_array[strict_note_mask]
                # Filter out "None"
                actual_corrections = [c for c in note_corrections if c != "None"]
                if actual_corrections:
                    from collections import Counter
                    # Get the most common correction type in this note island
                    correction_type = Counter(actual_corrections).most_common(1)[0][0]
                    correction_applied = True
            
            median_confidence = np.nanmedian(voicing_prob[strict_note_mask]) if voicing_prob is not None else np.nan

            dtw_results.append({
                'Note_Index': i + 1,
                'Expected_Note': note_name,
                'Median_Detected_Pitch_Hz': median_f0,
                'Expected_Target_Pitch_Hz': expected_hz,
                'Deviation_Cents': deviation_cents,
                'Deviation_Hz': deviation_hz,
                'Median_RMS_dBFS': median_rms_dbfs,
                'Median_RMS_dBA': median_rms_dba,
                'Median_Confidence': median_confidence,
                'Correction_Applied': correction_applied,
                'Correction_Type': correction_type
            })
        else:
            # Safeguard for completely empty arrays (Missed or completely filtered out)
            dtw_results.append({
                'Note_Index': i + 1,
                'Expected_Note': note_name,
                'Median_Detected_Pitch_Hz': np.nan,
                'Expected_Target_Pitch_Hz': librosa.midi_to_hz(pitch) * (reference_pitch_hz / 440.0) if not np.isnan(pitch) else np.nan,
                'Deviation_Cents': np.nan,
                'Deviation_Hz': np.nan,
                'Median_RMS_dBFS': np.nan,
                'Median_RMS_dBA': np.nan,
                'Median_Confidence': np.nan,
                'Correction_Applied': False,
                'Correction_Type': "None"
            })
            
    return dtw_results

def process_dtw_alignment(midi_timing, f0_hz, audio_y, sr, final_mask, toggles, max_pitch_slope, hop_length=512):
    """
    Encapsulates the full DTW alignment, harmonic folding, and mask recalculation logic.
    Returns all variables required by the visualizer and metric calculator.
    """
    import librosa
    import numpy as np
    
    time_array = librosa.times_like(f0_hz, sr=sr, hop_length=hop_length)
    
    # 1. Alignment Mask
    force_global = toggles.get('force_global', True)
    mask, expected_pitch, warped_timeline, expected_note_index = get_alignment_mask(
        midi_timing, time_array, audio_y, sr, hop_length=hop_length, force_global=force_global
    )
    
    # 2. Harmonic Folding
    if toggles.get('harmonic_folding', True):
        folded_f0_hz, folded_f0_midi, correction_array = apply_harmonic_folding(f0_hz, expected_pitch)
    else:
        folded_f0_hz = f0_hz
        folded_f0_midi = librosa.hz_to_midi(folded_f0_hz)
        correction_array = np.full(len(f0_hz), "None", dtype=object)
        
    # 3. Slope Mask Recalculation
    folded_pitch_slope = np.concatenate(([0], np.abs(np.diff(folded_f0_midi))))
    if toggles.get('slope_filter', True):
        folded_slope_mask = (folded_pitch_slope <= max_pitch_slope) | np.isnan(folded_pitch_slope)
    else:
        folded_slope_mask = np.ones_like(folded_pitch_slope, dtype=bool)
        
    # 4. Strict Mask for visualization
    strict_mask = mask & final_mask & folded_slope_mask
    
    return time_array, expected_pitch, warped_timeline, expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask, correction_array


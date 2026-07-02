import librosa
import numpy as np

def get_instrument_fmin_fmax(instrument: str):
    """
    Returns the appropriate (fmin, fmax) frequency limits in Hz 
    for common string instruments to mitigate incorrect pitch detections
    (e.g., detecting harmonics or subharmonics outside the instrument's range).
    """
    instrument = instrument.lower()
    if instrument == 'violin':
        return librosa.note_to_hz('G3'), librosa.note_to_hz('C7')
    elif instrument == 'viola':
        return librosa.note_to_hz('C3'), librosa.note_to_hz('A6')
    elif instrument == 'cello':
        return librosa.note_to_hz('C2'), librosa.note_to_hz('E6')
    else:
        # Default fallback covering most orchestral strings
        return librosa.note_to_hz('C2'), librosa.note_to_hz('C7')

def extract_pitch_and_rms(audio_file, instrument, switch_prob, enable_freq_limits=True):
    """
    Loads audio, extracts pitch using pYIN, and calculates RMS energy.
    Ensures all arrays are exactly the same length.
    """
    audio_file.seek(0)
    y, sr = librosa.load(audio_file, sr=None)
    
    if enable_freq_limits:
        fmin_hz, fmax_hz = get_instrument_fmin_fmax(instrument)
    else:
        # A broad fallback covering the audible spectrum to simulate no limits
        fmin_hz, fmax_hz = librosa.note_to_hz('C0'), librosa.note_to_hz('G9')
        
    f0, voiced_flag, _ = librosa.pyin(
        y, 
        fmin=fmin_hz, 
        fmax=fmax_hz, 
        sr=sr,
        switch_prob=switch_prob
    )
    
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    
    # Ensure all arrays are exactly the same length before logical operations
    min_len = min(len(voiced_flag), len(rms))
    f0 = f0[:min_len]
    voiced_flag = voiced_flag[:min_len]
    rms = rms[:min_len]
    
    return y, sr, f0, voiced_flag, rms

def generate_filters(f0, voiced_flag, rms, rms_threshold, max_pitch_slope, enable_slope_filter=True):
    """
    Calculates the combined boolean mask for voiced frames, amplitude threshold, 
    and pitch stability (slope).
    """
    # --- Pitch Rate-of-Change (Derivative) Filter ---
    # Convert f0 to continuous MIDI, explicitly ignoring NaNs (unvoiced frames)
    midi = np.full_like(f0, np.nan)
    valid_f0_mask = ~np.isnan(f0)
    midi[valid_f0_mask] = librosa.hz_to_midi(f0[valid_f0_mask])
    
    # Calculate frame-to-frame absolute difference (slope). Prepend 0 to maintain array length.
    pitch_slope = np.concatenate(([0], np.abs(np.diff(midi))))
    
    if enable_slope_filter:
        # Keep frames where pitch slope is stable OR where the transition involves a NaN (the very first frame of a note)
        slope_mask = (pitch_slope <= max_pitch_slope) | np.isnan(pitch_slope)
    else:
        slope_mask = np.ones_like(pitch_slope, dtype=bool)

    # Combine all condition masks: Must be voiced AND loud enough AND vertically stable
    combined_mask = voiced_flag & (rms > rms_threshold) & slope_mask
    return combined_mask

def apply_duration_filter(combined_mask, min_frames, enable_duration_filter=True):
    """
    Searches for continuous blocks of 'True' in the mask. 
    Discards any blocks shorter than 'min_frames' and returns the final mask.
    """
    if not enable_duration_filter:
        return combined_mask
    final_mask = np.copy(combined_mask)
    padded_mask = np.concatenate(([False], final_mask, [False]))
    changes = np.diff(padded_mask.astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    
    for start, end in zip(starts, ends):
        duration = end - start
        if duration < min_frames:
            # Strip away the fragment because it didn't last long enough
            final_mask[start:end] = False
            
    return final_mask

def calculate_island_metrics(f0, final_mask, enable_locked_target=True):
    """
    Identifies the final isolated note islands after duration filtering,
    applies the Locked Target Rule (median MIDI value), and computes deviations.
    """
    padded_mask = np.concatenate(([False], final_mask, [False]))
    changes = np.diff(padded_mask.astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]

    deviation_cents_list = []
    deviation_hz_list = []
    detected_notes_sequence = []
    
    f0_target = np.full_like(f0, np.nan)
    full_deviation = np.full_like(f0, np.nan)
    
    for start, end in zip(starts, ends):
        island_f0 = f0[start:end]
        valid_mask = ~np.isnan(island_f0)
        valid_island_f0 = island_f0[valid_mask]
        
        if len(valid_island_f0) > 0:
            continuous_midi = librosa.hz_to_midi(valid_island_f0)
            
            if enable_locked_target:
                # --- Locked Target Rule ---
                island_median_midi = np.median(continuous_midi)
                locked_target_note = np.round(island_median_midi)
                
                note_name = librosa.midi_to_note(locked_target_note)
                detected_notes_sequence.append(note_name)
                
                island_deviation = (continuous_midi - locked_target_note) * 100
                
                target_hz = librosa.midi_to_hz(locked_target_note)
                island_deviation_hz = valid_island_f0 - target_hz
                
                # For f0_target
                target_hz_array = np.full_like(valid_island_f0, target_hz)
            else:
                # Frame-by-frame target (No locked target)
                target_note_array = np.round(continuous_midi)
                
                # Just append the median note name for sequence comparison
                note_name = librosa.midi_to_note(np.round(np.median(continuous_midi)))
                detected_notes_sequence.append(note_name)
                
                island_deviation = (continuous_midi - target_note_array) * 100
                target_hz_array = librosa.midi_to_hz(target_note_array)
                island_deviation_hz = valid_island_f0 - target_hz_array
                
            deviation_cents_list.extend(island_deviation)
            deviation_hz_list.extend(island_deviation_hz)
            
            island_indices = np.arange(start, end)
            valid_full_indices = island_indices[valid_mask]
            
            f0_target[valid_full_indices] = target_hz_array
            full_deviation[valid_full_indices] = island_deviation
            
    return {
        'starts': starts,
        'deviation_cents_list': deviation_cents_list,
        'deviation_hz_list': deviation_hz_list,
        'detected_notes_sequence': detected_notes_sequence,
        'f0_target': f0_target,
        'full_deviation': full_deviation
    }

def analyze_intonation(y, sr, f0, voiced_flag, rms, rms_threshold=0.01, min_frames=10, max_pitch_slope=3.0, toggles=None):
    """
    Core engine for intonation analysis.
    Accepts pre-extracted pYIN pitch arrays and orchestrates masking, filtering, and metric calculation.
    """
    if toggles is None:
        toggles = {
            'freq_limits': True,
            'slope_filter': True,
            'duration_filter': True,
            'locked_target': True,
            'octave_folding': True
        }
        
    enable_slope_filter = toggles.get('slope_filter', True)
    enable_duration_filter = toggles.get('duration_filter', True)
    enable_locked_target = toggles.get('locked_target', True)

    # 2. Filtering
    combined_mask = generate_filters(f0, voiced_flag, rms, rms_threshold, max_pitch_slope, enable_slope_filter)
    final_mask = apply_duration_filter(combined_mask, min_frames, enable_duration_filter)
    
    # 3. Metrics Calculation
    metrics = calculate_island_metrics(f0, final_mask, enable_locked_target)
    
    # 4. Compilation
    results = {
        'y': y,
        'f0': f0,
        'sr': sr,
        'rms': rms,
        'final_mask': final_mask,
        'f0_target': metrics['f0_target'],
        'full_deviation': metrics['full_deviation'],
        'deviation_cents_list': metrics['deviation_cents_list'],
        'deviation_hz_list': metrics['deviation_hz_list'],
        'detected_notes_sequence': metrics['detected_notes_sequence'],
        'success': len(metrics['deviation_cents_list']) > 0
    }
    
    if results['success']:
        deviation_cents = np.array(metrics['deviation_cents_list'])
        deviation_hz = np.array(metrics['deviation_hz_list'])
        results['mean_dev'] = np.mean(deviation_cents)
        results['std_dev'] = np.std(deviation_cents)
        results['mean_dev_hz'] = np.mean(deviation_hz)
        results['std_dev_hz'] = np.std(deviation_hz)
        results['frame_count'] = len(deviation_cents)
        results['note_count'] = len(metrics['starts'])
        
    return results

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

def analyze_intonation(audio_file, instrument='voice', switch_prob=0.01, rms_threshold=0.01, min_frames=10, max_pitch_slope=3.0):
    """
    Core engine for pitch extraction and intonation analysis.
    Returns a dictionary of metrics and arrays necessary for plotting.
    """
    # 1. Audio Loading
    audio_file.seek(0)
    y, sr = librosa.load(audio_file, sr=None)
    
    # 2. Pitch Extraction (pYIN)
    fmin_hz, fmax_hz = get_instrument_fmin_fmax(instrument)
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, 
        fmin=fmin_hz, 
        fmax=fmax_hz, 
        sr=sr,
        switch_prob=switch_prob
    )
    
    # 3. Masking and Filtering
    # Calculate the Root Mean Square (RMS) energy to find the volume of each frame
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    


    # Ensure all arrays are exactly the same length before logical operations
    min_len = min(len(voiced_flag), len(rms))
    f0 = f0[:min_len]
    voiced_flag = voiced_flag[:min_len]
    rms = rms[:min_len]
    
    # --- Pitch Rate-of-Change (Derivative) Filter ---
    # Convert f0 to continuous MIDI, explicitly ignoring NaNs (unvoiced frames)
    midi = np.full_like(f0, np.nan)
    valid_f0_mask = ~np.isnan(f0)
    midi[valid_f0_mask] = librosa.hz_to_midi(f0[valid_f0_mask])
    
    # Calculate frame-to-frame absolute difference (slope). Prepend 0 to maintain array length.
    pitch_slope = np.concatenate(([0], np.abs(np.diff(midi))))
    
    # Keep frames where pitch slope is stable OR where the transition involves a NaN (the very first frame of a note)
    slope_mask = (pitch_slope <= max_pitch_slope) | np.isnan(pitch_slope)

    # Combine all condition masks: Must be voiced AND loud enough AND vertically stable
    combined_mask = voiced_flag & (rms > rms_threshold) & slope_mask
    
    # --- Duration Filtering (Stable Islands) ---
    # Search for continuous blocks of 'True' in the mask. Discard any blocks shorter than 'min_frames'
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

    # 4. Math and Locked Target Rule
    # Re-identify the final isolated note islands after duration filtering
    padded_mask = np.concatenate(([False], final_mask, [False]))
    changes = np.diff(padded_mask.astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]

    deviation_cents_list = []
    deviation_hz_list = []
    detected_notes_sequence = []
    
    # Prepare tracking arrays mapping strictly back to the original timeline length for Plotly
    f0_target = np.full_like(f0, np.nan)
    full_deviation = np.full_like(f0, np.nan)
    
    # Iterate through each isolated note ('island') individually
    for start, end in zip(starts, ends):
        island_f0 = f0[start:end]
        valid_mask = ~np.isnan(island_f0)
        valid_island_f0 = island_f0[valid_mask]
        
        if len(valid_island_f0) > 0:
            continuous_midi = librosa.hz_to_midi(valid_island_f0)
            
            # --- Locked Target Rule ---
            # Calculate the median MIDI value of the entire single note
            island_median_midi = np.median(continuous_midi)
            locked_target_note = np.round(island_median_midi)
            
            # Add to the chronological note sequence
            note_name = librosa.midi_to_note(locked_target_note)
            detected_notes_sequence.append(note_name)
            
            # Calculate deviation for every frame in this island strictly against the locked target
            island_deviation = (continuous_midi - locked_target_note) * 100
            deviation_cents_list.extend(island_deviation)
            
            # Calculate Hz deviation
            target_hz = librosa.midi_to_hz(locked_target_note)
            island_deviation_hz = valid_island_f0 - target_hz
            deviation_hz_list.extend(island_deviation_hz)
            
            # Map these isolated calculations safely back to their proper global indices for the timeline
            island_indices = np.arange(start, end)
            valid_full_indices = island_indices[valid_mask]
            
            f0_target[valid_full_indices] = target_hz
            full_deviation[valid_full_indices] = island_deviation
            
    # Compile results
    results = {
        'y': y,
        'f0': f0,
        'final_mask': final_mask,
        'f0_target': f0_target,
        'full_deviation': full_deviation,
        'sr': sr,
        'deviation_cents_list': deviation_cents_list,
        'deviation_hz_list': deviation_hz_list,
        'detected_notes_sequence': detected_notes_sequence,
        'success': len(deviation_cents_list) > 0
    }
    

    
    if results['success']:
        deviation_cents = np.array(deviation_cents_list)
        deviation_hz = np.array(deviation_hz_list)
        results['mean_dev'] = np.mean(deviation_cents)
        results['std_dev'] = np.std(deviation_cents)
        results['mean_dev_hz'] = np.mean(deviation_hz)
        results['std_dev_hz'] = np.std(deviation_hz)
        results['frame_count'] = len(deviation_cents)
        results['note_count'] = len(starts)
        
    return results

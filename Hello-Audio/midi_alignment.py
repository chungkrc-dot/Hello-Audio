import numpy as np


def get_midi_chroma(midi_notes, sr, hop_length):
    """
    Synthesizes a basic sine-wave audio track from the MIDI score and extracts 12-bin Chroma CQT.
    """
    import numpy as np
    import librosa
    
    if not midi_notes:
        return np.array([])
        
    first_start = midi_notes[0]['Start_Time'] if isinstance(midi_notes[0], dict) else getattr(midi_notes[0], 'Start_Time', 0)
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
            
    chroma = librosa.feature.chroma_cqt(y=y_midi, sr=sr, hop_length=hop_length)
    return chroma

def get_audio_chroma(audio_y, sr, hop_length):
    """
    Extracts the 12-bin Chroma CQT from the raw audio waveform.
    """
    import librosa
    return librosa.feature.chroma_cqt(y=audio_y, sr=sr, hop_length=hop_length)

def compute_dtw_path(midi_chroma, audio_chroma):
    """
    Computes the Dynamic Time Warping (DTW) path using multi-dimensional Chroma features.
    """
    import numpy as np
    import librosa
    
    # Subsequence DTW requires the shorter query sequence to be the first argument (X) 
    # and the longer reference sequence to be the second argument (Y).
    D, wp = librosa.sequence.dtw(
        midi_chroma, 
        audio_chroma, 
        metric='cosine', 
        subseq=True
    )
    
    # Crucial Matrix formatting: Because we swapped the inputs to (midi, audio), 
    # librosa returns a warping_path where column 0 = MIDI indices and column 1 = Audio indices.
    # We must swap the columns using np.fliplr so that the returned format remains 
    # (audio_index, expected_midi_index). This ensures the downstream 
    # generate_valid_mask and diagnostic plotting functions do not break.
    wp = np.fliplr(wp)
    
    return wp


def get_alignment_mask(midi_notes, time_array, audio_y, sr, hop_length=512):
    """
    Orchestrates the DTW alignment process using Chroma vectors and builds a continuous
    absolute-time bridge to map MIDI notes directly onto the audio timeline.
    """
    import numpy as np
    import librosa
    
    # 1. Generate multi-dimensional Chroma features for robust DTW
    midi_chroma = get_midi_chroma(midi_notes, sr, hop_length)
    audio_chroma = get_audio_chroma(audio_y, sr, hop_length)
    
    # 2. Compute DTW on Chroma
    # wp is formatted as [audio_frame, midi_frame]
    wp = compute_dtw_path(midi_chroma, audio_chroma)
    
    # 3. Convert DTW path to absolute time mapping
    first_start = midi_notes[0]['Start_Time'] if isinstance(midi_notes[0], dict) else getattr(midi_notes[0], 'Start_Time', 0)
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

def apply_octave_folding(f0_hz, expected_midi_pitch):
    """
    Globally folds an audio f0 pitch array into the nearest octave of the expected MIDI target.
    This ensures both visual graphs and metric tables share the same corrected harmonic data.
    """
    import numpy as np
    import librosa
    
    f0_midi = librosa.hz_to_midi(f0_hz)
    valid_mask = ~np.isnan(f0_midi) & ~np.isnan(expected_midi_pitch)
    
    octave_offsets = np.zeros_like(f0_midi)
    octave_offsets[valid_mask] = np.round((f0_midi[valid_mask] - expected_midi_pitch[valid_mask]) / 12.0)
    
    folded_f0_midi = f0_midi - (octave_offsets * 12.0)
    folded_f0_hz = librosa.midi_to_hz(folded_f0_midi)
    
    return folded_f0_hz, folded_f0_midi

def calculate_dtw_metrics(midi_notes, time_array, f0, rms, final_mask, warped_midi_timeline):
    """
    Extracts explicit note-by-note intonation metrics derived from the DTW warping path.
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
            
            # Deviation from the TRUE MIDI pitch (cents)
            deviation_cents = (median_midi - pitch) * 100
            
            # Convert deviation to Hz
            expected_hz = librosa.midi_to_hz(pitch)
            deviation_hz = median_f0 - expected_hz
            
            # RMS in dBFS
            median_rms_dbfs = 20 * np.log10(np.nanmedian(note_rms) + 1e-10)
            
            # RMS in dBA
            median_rms_dba = median_rms_dbfs + librosa.A_weighting(median_f0)
            
            dtw_results.append({
                'Note_Index': i + 1,
                'Expected_Note': note_name,
                'Median_Detected_Pitch_Hz': median_f0,
                'Expected_Target_Pitch_Hz': expected_hz,
                'Deviation_Cents': deviation_cents,
                'Deviation_Hz': deviation_hz,
                'Median_RMS_dBFS': median_rms_dbfs,
                'Median_RMS_dBA': median_rms_dba
            })
        else:
            # Safeguard for completely empty arrays (Missed or completely filtered out)
            dtw_results.append({
                'Note_Index': i + 1,
                'Expected_Note': note_name,
                'Median_Detected_Pitch_Hz': np.nan,
                'Expected_Target_Pitch_Hz': librosa.midi_to_hz(pitch) if not np.isnan(pitch) else np.nan,
                'Deviation_Cents': np.nan,
                'Deviation_Hz': np.nan,
                'Median_RMS_dBFS': np.nan,
                'Median_RMS_dBA': np.nan
            })
            
    return dtw_results


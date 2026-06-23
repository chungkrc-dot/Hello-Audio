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
    
    for note in midi_notes:
        start_time = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
        end_time = note['End_Time'] if isinstance(note, dict) else getattr(note, 'End_Time', 0)
        pitch = note['Pitch'] if isinstance(note, dict) else getattr(note, 'Pitch', np.nan)
        
        # Find which audio frames' warped timeline falls within this note's duration
        note_mask = (warped_midi_timeline >= start_time) & (warped_midi_timeline < end_time)
        
        valid_dtw_mask[note_mask] = True
        expected_audio_pitch[note_mask] = pitch
        
    return valid_dtw_mask, expected_audio_pitch

def plot_alignment_diagnostics(time_array, audio_f0_midi, expected_audio_pitch, valid_dtw_mask):
    """
    Plots a diagnostic graph to visually verify matched vs extraneous pitches.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Ensure all arrays match the time_array length safely
    min_len = min(len(time_array), len(audio_f0_midi), len(expected_audio_pitch), len(valid_dtw_mask))
    time_array = time_array[:min_len]
    audio_f0_midi = audio_f0_midi[:min_len]
    expected_audio_pitch = expected_audio_pitch[:min_len]
    valid_dtw_mask = valid_dtw_mask[:min_len]
    
    # 1. Plot expected MIDI track as a thick gray background
    ax.plot(time_array, expected_audio_pitch, color='gray', linewidth=4, alpha=0.5, label='Expected MIDI Score')
    
    # 2. Isolate matched and unmatched audio pitches
    matched_audio = np.full_like(audio_f0_midi, np.nan)
    unmatched_audio = np.full_like(audio_f0_midi, np.nan)
    
    matched_audio[valid_dtw_mask] = audio_f0_midi[valid_dtw_mask]
    unmatched_audio[~valid_dtw_mask] = audio_f0_midi[~valid_dtw_mask]
    
    # 3. Plot them with Blue/Yellow colors
    ax.plot(time_array, matched_audio, 'b.', markersize=4, label='Matched Pitches')
    ax.plot(time_array, unmatched_audio, 'y.', markersize=4, label='Extraneous Pitches')
    
    ax.set_title("DTW Alignment Diagnostics")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("MIDI Pitch")
    ax.legend(loc='best')
    ax.grid(True)
    
    # Optimize layout
    fig.tight_layout()
    
    return fig

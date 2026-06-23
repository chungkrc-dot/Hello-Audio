import librosa
import numpy as np

def get_instrument_fmin_fmax(instrument: str):
    """
    Returns the appropriate (fmin, fmax) frequency limits in Hz 
    for common string instruments to mitigate incorrect detections.
    """
    instrument = instrument.lower()
    if instrument == 'violin':
        return librosa.note_to_hz('G3'), librosa.note_to_hz('C7')
    elif instrument == 'viola':
        return librosa.note_to_hz('C3'), librosa.note_to_hz('A6')
    elif instrument == 'cello':
        return librosa.note_to_hz('C2'), librosa.note_to_hz('E6')
    else:
        # Default fallback
        return librosa.note_to_hz('C2'), librosa.note_to_hz('C7')

def analyze_intonation(y, sr, fmin=65.4, fmax=2093.0, switch_prob=0.005, rms_threshold=0.01, min_frames=10):
    """
    Analyzes musician intonation deviation by isolating steady-state notes and 
    calculating their deviation from the nearest semitone.
    
    Parameters:
    - y: audio time series array
    - sr: sample rate
    - fmin: minimum frequency for pYIN (default 65.4 Hz, C2)
    - fmax: maximum frequency for pYIN (default 2093.0 Hz, C7)
    - switch_prob: transition probability for pYIN HMM (default 0.005)
    - rms_threshold: minimum RMS energy threshold for a frame to be considered active
    - min_frames: minimum consecutive active frames to be considered a stable note
    
    Returns:
    - continuous_midi: array of MIDI pitches for valid frames
    - target_note: array of nearest semitone integer MIDI notes for valid frames
    - deviation_cents: array of pitch deviation in cents from the target note
    """
    
    # 1. Pitch Extraction (Standard pYIN)
    # switch_prob lowered to penalize rapid toggling, favoring longer sustained notes
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, 
        fmin=fmin, 
        fmax=fmax, 
        sr=sr,
        switch_prob=switch_prob
    )
    
    # 2. Amplitude Thresholding
    # Compute the RMS energy for each frame. 
    # librosa.pyin uses a default hop_length of 512 and frame_length of 2048, 
    # so we match those parameters for RMS to align the frames.
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    
    # Ensure arrays are exactly the same length 
    # (sometimes off by 1 frame due to padding differences between functions)
    min_len = min(len(voiced_flag), len(rms))
    f0 = f0[:min_len]
    voiced_flag = voiced_flag[:min_len]
    rms = rms[:min_len]
    
    # Create combined boolean mask (voiced AND exceeds RMS threshold)
    combined_mask = voiced_flag & (rms > rms_threshold)
    
    # 3. Duration Filtering (Stable Islands)
    final_mask = np.copy(combined_mask)
    
    # Find contiguous blocks (islands) of True frames
    # Pad with False to easily detect edges at the start/end of the array
    padded_mask = np.concatenate(([False], final_mask, [False]))
    changes = np.diff(padded_mask.astype(int))
    
    # starts is where changes == 1 (False -> True)
    # ends is where changes == -1 (True -> False)
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    
    for start, end in zip(starts, ends):
        duration = end - start
        if duration < min_frames:
            # Flip those frames to False to strip short transitional blips
            final_mask[start:end] = False
            
    # 4. Intonation Deviation Calculation
    # Use only frames where final mask is True
    valid_f0 = f0[final_mask]
    
    # Filter out any possible NaN values from pYIN just to be safe
    valid_f0 = valid_f0[~np.isnan(valid_f0)]
    
    if len(valid_f0) == 0:
        return np.array([]), np.array([]), np.array([])
        
    # Convert f0 to continuous MIDI pitches
    continuous_midi = librosa.hz_to_midi(valid_f0)
    
    # Calculate target note (round to nearest whole integer/semitone)
    target_note = np.round(continuous_midi)
    
    # Calculate deviation in cents
    deviation_cents = (continuous_midi - target_note) * 100
    
    return continuous_midi, target_note, deviation_cents


if __name__ == "__main__":
    # Example usage:
    # y, sr = librosa.load("your_audio_file.wav")
    
    # Generate a dummy signal to demonstrate the function
    print("Generating a test signal (A4 with vibrato and some intonation drift)...")
    sr_test = 22050
    t = np.linspace(0, 3, 3 * sr_test)
    
    # Base frequency drifts from 440 Hz (A4) to 445 Hz, with vibrato
    freq_drift = np.linspace(440, 445, len(t))
    vibrato = 3 * np.sin(2 * np.pi * 5 * t)
    y_test = 0.5 * np.sin(2 * np.pi * (freq_drift + vibrato) * t)
    
    print("Analyzing intonation...")
    midi, target, cents = analyze_intonation(
        y_test, 
        sr_test, 
        switch_prob=0.005, 
        rms_threshold=0.01, 
        min_frames=10
    )
    
    if len(cents) > 0:
        print(f"Extracted {len(cents)} valid steady-state frames.")
        print(f"Average deviation: {np.mean(cents):.2f} cents")
        print(f"Standard deviation: {np.std(cents):.2f} cents")
        print(f"Target notes identified: {np.unique(target)}")
    else:
        print("No stable notes detected.")

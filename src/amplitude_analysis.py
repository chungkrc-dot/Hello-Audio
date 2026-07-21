"""
amplitude_analysis.py
---------------------
Core engine for calculating acoustic intensity metrics.
This module processes raw audio signals to extract global Root Mean Square (RMS) energy.
It performs both absolute digital scaling (dBFS) and psychoacoustic human-hearing 
perceptual weighting (dBA) across the entire recording.
"""
import librosa
import numpy as np

def analyze_amplitude(y, sr):
    """
    Analyzes the global amplitude of an audio file.
    Returns the mean RMS in dBFS (Full Scale) and dBA (A-weighted).
    """
    # Calculate global RMS amplitude in dBFS using time-domain for accuracy
    # (prevents the ~-4.28 dB bias caused by STFT windowing energy loss)
    rms_time = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    
    # Calculate STFT magnitude for A-weighting derivation
    S, _ = librosa.magphase(librosa.stft(y, n_fft=2048, hop_length=512))
    rms_stft = librosa.feature.rms(S=S)[0]
    
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        # Calculate A-weighted RMS for the entire recording
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        a_weights_amp = 10 ** (librosa.A_weighting(freqs) / 20)
    S_a = S * a_weights_amp[:, np.newaxis]
    rms_stft_a = librosa.feature.rms(S=S_a)[0]
    
    # Calculate the relative A-weighting attenuation factor per frame
    # and apply it to the accurate time-domain RMS to create a calibrated dBA RMS
    ratio = rms_stft_a / np.clip(rms_stft, 1e-10, None)
    rms_time_a = rms_time * ratio
    
    mean_dbfs = 20 * np.log10(np.clip(np.mean(rms_time), 1e-10, None))
    mean_dba = 20 * np.log10(np.clip(np.mean(rms_time_a), 1e-10, None))
    
    return {
        'mean_dbfs': mean_dbfs,
        'mean_dba': mean_dba
    }

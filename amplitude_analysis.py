import librosa
import numpy as np

def analyze_amplitude(audio_file):
    """
    Analyzes the global amplitude of an audio file.
    Returns the mean RMS in dBFS (Full Scale) and dBA (A-weighted).
    """
    audio_file.seek(0)
    y, sr = librosa.load(audio_file, sr=None)
    
    # Compute amplitude spectrogram
    S, _ = librosa.magphase(librosa.stft(y, n_fft=2048, hop_length=512))
    rms = librosa.feature.rms(S=S)[0]
    
    # Calculate A-weighted RMS for the entire recording
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    a_weights_amp = 10 ** (librosa.A_weighting(freqs) / 20)
    S_a = S * a_weights_amp[:, np.newaxis]
    rms_a = librosa.feature.rms(S=S_a)[0]
    
    mean_dbfs = 20 * np.log10(np.clip(np.mean(rms), 1e-10, None))
    mean_dba = 20 * np.log10(np.clip(np.mean(rms_a), 1e-10, None))
    
    return {
        'mean_dbfs': mean_dbfs,
        'mean_dba': mean_dba
    }

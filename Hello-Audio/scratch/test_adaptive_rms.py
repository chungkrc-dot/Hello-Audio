import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from src.pitch_engine import analyze_intonation

def test_adaptive_rms():
    print("Running Adaptive RMS Test...")
    # Simulate a 10-second audio track (430 frames at 512 hop_length on 22050 sr)
    # The first 2 seconds (86 frames) are silence/noise.
    
    # 1. Clean track (digital silence is 0, notes are 0.5)
    rms_clean = np.concatenate((np.zeros(86), np.full(344, 0.5)))
    f0_clean = np.full(430, 440.0)
    voiced_flag_clean = np.full(430, True)
    
    # 2. Noisy track (room noise is 0.05, notes are 0.5)
    rms_noisy = np.concatenate((np.full(86, 0.05), np.full(344, 0.5)))
    f0_noisy = np.full(430, 440.0)
    voiced_flag_noisy = np.full(430, True)
    
    # Set static threshold to 0.01 (too low for noisy track)
    static_threshold = 0.01
    
    toggles_adaptive_off = {
        'freq_limits': False,
        'slope_filter': False,
        'duration_filter': False,
        'locked_target': False,
        'adaptive_rms': False
    }
    
    toggles_adaptive_on = {
        'freq_limits': False,
        'slope_filter': False,
        'duration_filter': False,
        'locked_target': False,
        'adaptive_rms': True
    }
    
    print("\n--- Testing Noisy Track ---")
    res_noisy_off = analyze_intonation(None, 22050, f0_noisy, voiced_flag_noisy, rms_noisy, rms_threshold=static_threshold, min_frames=1, max_pitch_slope=3.0, toggles=toggles_adaptive_off)
    print(f"Adaptive OFF: Frames passing threshold = {np.sum(res_noisy_off['final_mask'])}")
    
    res_noisy_on = analyze_intonation(None, 22050, f0_noisy, voiced_flag_noisy, rms_noisy, rms_threshold=static_threshold, min_frames=1, max_pitch_slope=3.0, toggles=toggles_adaptive_on)
    print(f"Adaptive ON: Frames passing threshold = {np.sum(res_noisy_on['final_mask'])}")
    
    # Assertions
    # With adaptive off, the noise (0.05) > threshold (0.01), so all 430 frames pass.
    assert np.sum(res_noisy_off['final_mask']) == 430, "Adaptive OFF failed"
    # With adaptive on, the 10th percentile is 0.05. Effective threshold is 0.10. 
    # So the 86 noise frames should be gated out, leaving 344 notes.
    assert np.sum(res_noisy_on['final_mask']) == 344, "Adaptive ON failed"
    
    print("\n--- Testing Clean Track ---")
    res_clean_on = analyze_intonation(None, 22050, f0_clean, voiced_flag_clean, rms_clean, rms_threshold=static_threshold, min_frames=1, max_pitch_slope=3.0, toggles=toggles_adaptive_on)
    print(f"Adaptive ON (Clean): Frames passing threshold = {np.sum(res_clean_on['final_mask'])}")
    
    # With adaptive on, 10th percentile is 0. Effective threshold is max(0.01, 0 * 2.0) = 0.01.
    # So the 86 silence frames (0.0) are gated out, leaving 344 notes.
    assert np.sum(res_clean_on['final_mask']) == 344, "Adaptive ON (Clean) failed"
    
    print("\nAll tests passed successfully!")

if __name__ == "__main__":
    test_adaptive_rms()

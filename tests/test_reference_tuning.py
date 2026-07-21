"""
Functional test: configurable reference tuning.
Generates a 442 Hz sine wave, runs the pipeline with reference_pitch_hz=442.0,
and verifies the deviation from A4 is ~0 cents rather than ~+7.9 cents.
"""
import numpy as np
import io
import soundfile as sf
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation


def generate_sine_wav(freq_hz, duration=2.0, sr=44100):
    t = np.arange(int(sr * duration)) / sr
    y = 0.5 * np.sin(2 * np.pi * freq_hz * t)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format='WAV')
    buf.seek(0)
    return buf


def test_reference_tuning():
    freq = 442.0
    audio = generate_sine_wav(freq)

    y, sr, f0, voiced_flag, rms, voicing_prob = extract_pitch_and_rms(
        audio, instrument="Violin", switch_prob=0.005, enable_freq_limits=True
    )

    toggles = {
        'freq_limits': True,
        'slope_filter': False,
        'duration_filter': False,
        'locked_target': True,
        'adaptive_rms': False
    }

    # With default A=440: expect ~+7.9 cents bias
    res_440 = analyze_intonation(
        y, sr, f0, voiced_flag, rms,
        rms_threshold=0.001, min_frames=1, max_pitch_slope=3.0,
        toggles=toggles, reference_pitch_hz=440.0
    )
    assert res_440['success'], "A=440 analysis should succeed"
    mean_440 = res_440['mean_dev']

    # With A=442: expect ~0 cents
    audio.seek(0)
    y2, sr2, f02, vf2, rms2, vp2 = extract_pitch_and_rms(
        audio, instrument="Violin", switch_prob=0.005, enable_freq_limits=True
    )
    res_442 = analyze_intonation(
        y2, sr2, f02, vf2, rms2,
        rms_threshold=0.001, min_frames=1, max_pitch_slope=3.0,
        toggles=toggles, reference_pitch_hz=442.0
    )
    assert res_442['success'], "A=442 analysis should succeed"
    mean_442 = res_442['mean_dev']

    print(f"442 Hz sine @ A=440 reference: mean deviation = {mean_440:+.2f} cents")
    print(f"442 Hz sine @ A=442 reference: mean deviation = {mean_442:+.2f} cents")

    assert abs(mean_440) > 5.0, f"A=440 should show significant bias, got {mean_440:.2f}c"
    assert abs(mean_442) < 3.0, f"A=442 should be near zero, got {mean_442:.2f}c"

    print("\nPASSED: Reference tuning correction works correctly.")


if __name__ == "__main__":
    test_reference_tuning()

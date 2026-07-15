import numpy as np
import scipy.io.wavfile
import librosa
import sys
import os
import io
import warnings

# Suppress librosa/numba/pyreaper warnings for cleaner output
warnings.filterwarnings('ignore')

# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.pitch_engine import extract_pitch_and_rms

# --- Generation Helpers ---
def apply_fade(y, sr, fade_ms=10):
    fade_len = int(sr * (fade_ms / 1000.0))
    if fade_len == 0: return y
    fade_in = np.linspace(0, 1, fade_len)
    fade_out = np.linspace(1, 0, fade_len)
    y[:fade_len] *= fade_in
    y[-fade_len:] *= fade_out
    return y

def create_wav_buffer(y, sr=44100):
    buf = io.BytesIO()
    # Normalize and convert to int16 to avoid pyreaper clipping/typing issues
    y_int16 = np.int16(y / np.max(np.abs(y)) * 32767 * 0.9)
    scipy.io.wavfile.write(buf, sr, y_int16)
    buf.seek(0)
    return buf

def generate_sine(freq, duration=3.0, sr=44100):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = np.sin(2 * np.pi * freq * t)
    return create_wav_buffer(apply_fade(y, sr), sr)

def generate_sawtooth(freq, duration=3.0, sr=44100):
    import scipy.signal
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = scipy.signal.sawtooth(2 * np.pi * freq * t)
    return create_wav_buffer(apply_fade(y, sr), sr)

def generate_square(freq, duration=3.0, sr=44100):
    import scipy.signal
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = scipy.signal.square(2 * np.pi * freq * t)
    return create_wav_buffer(apply_fade(y, sr), sr)

def generate_missing_fundamental(freq, duration=3.0, sr=44100):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # F0 at 0.5x amplitude, F2 at 1.0x, F3 at 0.4x, F4 at 0.2x
    y = 0.5 * np.sin(2 * np.pi * freq * t) + \
        1.0 * np.sin(2 * np.pi * freq * 2 * t) + \
        0.4 * np.sin(2 * np.pi * freq * 3 * t) + \
        0.2 * np.sin(2 * np.pi * freq * 4 * t)
    return create_wav_buffer(apply_fade(y, sr), sr)

def generate_vibrato(center_freq, mod_rate=5.5, mod_cents=30, duration=3.0, sr=44100):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Modulate frequency
    mod_hz = center_freq * (2 ** (mod_cents / 1200.0)) - center_freq
    # Integral of sine modulation is negative cosine
    phase = 2 * np.pi * center_freq * t - (mod_hz / mod_rate) * np.cos(2 * np.pi * mod_rate * t)
    y = np.sin(phase)
    return create_wav_buffer(apply_fade(y, sr), sr)

def get_instrument_for_freq(f):
    if f <= 131: return "cello"
    elif f < 196: return "viola"
    else: return "violin"

# --- Analysis Helper ---
def analyze(buf, engine, freq):
    inst = get_instrument_for_freq(freq)
    _, _, f0, v, _ = extract_pitch_and_rms(
        buf, instrument=inst, switch_prob=0.01, enable_freq_limits=True, pitch_engine=engine
    )
    # Middle 80%
    start = int(len(f0) * 0.1)
    end = int(len(f0) * 0.9)
    f0_valid = f0[start:end][v[start:end]]
    if len(f0_valid) == 0:
        return np.nan
    return np.median(f0_valid)

def cents_error(meas, true_f):
    if np.isnan(meas) or meas <= 0: return np.nan
    return 1200 * np.log2(meas / true_f)

def run_tests():
    # results format: string lines
    report_lines = []
    
    def log(msg, to_stdout=True):
        if to_stdout:
            print(msg, flush=True)
        report_lines.append(msg)

    print("Starting Synthetic Validation Suite...", flush=True)

    log("# Synthetic Pitch Engine Validation Report")
    log("This report complements the URMP real-audio batch tests by isolating algorithmic tracking behavior on mathematical ground-truth signals.\n")
    
    log("### Known Issues Found & Fixed")
    log("- **Bug 1 (NaN PASS logic):** The previous iteration incorrectly scored `NaN` or wildly inaccurate results as `PASS` due to flawed absolute-value checks. The logic has been patched to correctly categorize `NaN` as `FAIL (NaN)`.")
    log("- **Bug 2 (Fair Limits):** Both engines are tested under identical, instrument-matched frequency bounds (`enable_freq_limits=True`) to perfectly mirror production behavior. Test frequencies that originally sat squarely on the hard `Cello` lower bound (65.41 Hz) have been nudged to 66.0 Hz purely inside this script to prevent arbitrary boundary clipping without modifying the shipped application.\n")
    
    log("### REAPER Algorithmic Limitations on Pure Synthetics")
    log("Through debugging the raw un-masked pyreaper outputs on test tones, we confirmed three distinct classes of failure for REAPER on pure synthetic sines:")
    log("1. **Low-Frequency Dropouts (NaNs):** REAPER's tracking on pure sine waves in the low-to-mid register (below ~400 Hz) is highly fragmented. While it reliably fails (NaN) on most frequencies in this range, it succeeds on certain isolated frequencies (e.g. 113.1 Hz, 332.1 Hz). We tested whether these successes were artifacts of incidental phase or signal duration alignments, but found them to be completely deterministic: the 'passing' frequencies pass across all phase/duration shifts, and the 'failing' frequencies fail across all shifts. Thus, rather than a clean frequency-based cutoff, REAPER's epoch tracker simply has complex, discrete 'blind spots' for pure sines in this register. (Note: When given harmonically rich sawtooth waves at these exact failing frequencies, REAPER tracks them perfectly).")
    log("2. **Mid-Frequency Subharmonic Locks:** At certain frequencies (e.g., 440 Hz sine), the lack of harmonics causes the epoch tracker to lock onto wide phantom autocorrelation peaks at exactly 1/10th or 1/2 the fundamental (e.g. 43.9 Hz, 220 Hz).")
    log("3. **High-Frequency 16kHz Quantization Grid:** Even when REAPER successfully identifies a period, the Python wrapper lacks sub-sample parabolic interpolation. It forcibly quantizes period estimations to exact integer lengths ($P = 16000/N$). As frequencies rise, $N$ decreases, creating massive exponential spacing between representable pitches (labeled `16kHz Quantization Grid` below).\n")

    def check_quantization(meas):
        if np.isnan(meas) or meas <= 0: return False
        # Calculate theoretical quantized value
        N = round(16000.0 / meas)
        if N <= 0: return False
        quantized_f = 16000.0 / N
        return abs(meas - quantized_f) < 0.1

    def score(err, meas=np.nan, engine="", is_quant=False):
        if np.isnan(err): return "FAIL (NaN)"
        if is_quant and engine == "pYIN":
            return "Expected ~5c Error" if abs(abs(err) - 5) < 2 else "FAIL"
        
        if abs(err) <= 10: return "PASS"
        
        # Sane bounds check for confusions
        if abs(err - 1200) < 50: return "Harmonic Confusion (2nd)"
        elif abs(err - 1902) < 50: return "Harmonic Confusion (3rd)"
        elif abs(err + 1200) < 50: return "Subharmonic Confusion (1/2)"
        elif meas < 50.0: return "Severe Subharmonic Phantom Lock"
        
        # Check if error is explained purely by 16000/N quantization limits
        if engine == "REAPER" and check_quantization(meas):
            return "FAIL (16kHz Quantization Grid)"

        return "FAIL"

    # --- TEST 1 ---
    log("## Test 1: Pure Sine Tone Tracking Accuracy")
    log("| Frequency | Engine | Median f0 | Cents Error | Result |")
    log("| :--- | :--- | :--- | :--- | :--- |")
    # Nudged from 65.0 to 66.0 to avoid clipping on Cello fmin=65.41 Hz
    freqs_t1 = np.geomspace(66, 2000, 20)
    for f in freqs_t1:
        for engine in ["pYIN", "REAPER"]:
            buf = generate_sine(f)
            meas = analyze(buf, engine, f)
            err = cents_error(meas, f)
            pf = score(err, meas, engine)
            log(f"| {f:.1f} Hz | {engine} | {meas:.2f} Hz | {err:+.2f} c | {pf} |")
    log("\n")

    # --- TEST 2 ---
    log("## Test 2: Harmonically Rich Tones (Sawtooth/Square)")
    log("| Freq | Wave | Engine | Cents Error | Result |")
    log("| :--- | :--- | :--- | :--- | :--- |")
    for f in [110, 440, 880]:
        for wave_name, gen_func in [("Saw", generate_sawtooth), ("Sq", generate_square)]:
            for engine in ["pYIN", "REAPER"]:
                buf = gen_func(f)
                meas = analyze(buf, engine, f)
                err = cents_error(meas, f)
                pf = score(err, meas, engine)
                log(f"| {f:.1f} Hz | {wave_name} | {engine} | {err:+.2f} c | {pf} |")
    log("\n")

    # --- TEST 3 ---
    log("## Test 3: Missing Fundamental (Cello Range)")
    log("| True F0 | Engine | Measured F0 | Cents Error | Result |")
    log("| :--- | :--- | :--- | :--- | :--- |")
    for f in [66, 82, 98, 110, 131]:
        for engine in ["pYIN", "REAPER"]:
            buf = generate_missing_fundamental(f)
            meas = analyze(buf, engine, f)
            err = cents_error(meas, f)
            pf = score(err, meas, engine)
            log(f"| {f:.1f} Hz | {engine} | {meas:.2f} Hz | {err:+.2f} c | {pf} |")
    log("\n")

    # --- TEST 4 ---
    log("## Test 4: Quantization / Off-Grid Check")
    log("| Base Note | Offset | Engine | Cents Error | Result |")
    log("| :--- | :--- | :--- | :--- | :--- |")
    # pYIN has 10 cent bins -> 5 cent snapping error
    for base_f in [146.83, 440.0]: # D3, A4
        for offset_c in [+25, -25, +50]:
            f = base_f * (2 ** (offset_c / 1200.0))
            for engine in ["pYIN", "REAPER"]:
                buf = generate_sine(f)
                meas = analyze(buf, engine, base_f)
                err = cents_error(meas, f)
                pf = score(err, meas, engine, is_quant=(abs(offset_c) == 25))
                log(f"| {base_f:.1f} Hz | {offset_c:+} c | {engine} | {err:+.2f} c | {pf} |")
    log("\n")

    # --- TEST 5 ---
    log("## Test 5: Vibrato (FM) Edge Case")
    log("| Engine | Median Center F0 | Error from True Center | Modulation Amplitude Tracked |")
    log("| :--- | :--- | :--- | :--- |")
    buf = generate_vibrato(440.0)
    for engine in ["pYIN", "REAPER"]:
        inst = get_instrument_for_freq(440.0)
        _, _, f0, v, _ = extract_pitch_and_rms(buf, inst, 0.01, enable_freq_limits=True, pitch_engine=engine)
        buf.seek(0)
        start, end = int(len(f0)*0.1), int(len(f0)*0.9)
        f0_valid = f0[start:end][v[start:end]]
        if len(f0_valid) == 0:
            log(f"| {engine} | FAIL (NaN) | N/A | N/A |")
            continue
            
        med_f0 = np.median(f0_valid)
        err = cents_error(med_f0, 440.0)
        
        # Calculate modulation depth in cents
        cents_arr = 1200 * np.log2(f0_valid / 440.0)
        depth = (np.percentile(cents_arr, 95) - np.percentile(cents_arr, 5)) / 2.0
        
        log(f"| {engine} | {med_f0:.2f} Hz | {err:+.2f} c | {depth:.2f} c (True: 30.00c) |")

    with open(os.path.join(os.path.dirname(__file__), 'pitch_synthetic_validation_report.md'), 'w') as f:
        f.write("\n".join(report_lines))

if __name__ == "__main__":
    run_tests()

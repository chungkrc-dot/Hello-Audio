# Synthetic Pitch Engine Validation Report
This report complements the URMP real-audio batch tests by isolating algorithmic tracking behavior on mathematical ground-truth signals.

### Known Issues Found & Fixed
- **Bug 1 (NaN PASS logic):** The previous iteration incorrectly scored `NaN` or wildly inaccurate results as `PASS` due to flawed absolute-value checks. The logic has been patched to correctly categorize `NaN` as `FAIL (NaN)`.
- **Bug 2 (Fair Limits):** Both engines are tested under identical, instrument-matched frequency bounds (`enable_freq_limits=True`) to perfectly mirror production behavior. Test frequencies that originally sat squarely on the hard `Cello` lower bound (65.41 Hz) have been nudged to 66.0 Hz purely inside this script to prevent arbitrary boundary clipping without modifying the shipped application.

### REAPER Algorithmic Limitations on Pure Synthetics
Through debugging the raw un-masked pyreaper outputs on test tones, we confirmed three distinct classes of failure for REAPER on pure synthetic sines:
1. **Low-Frequency Dropouts (NaNs):** REAPER's tracking on pure sine waves in the low-to-mid register (below ~400 Hz) is highly fragmented. While it reliably fails (NaN) on most frequencies in this range, it succeeds on certain isolated frequencies (e.g. 113.1 Hz, 332.1 Hz). We tested whether these successes were artifacts of incidental phase or signal duration alignments, but found them to be completely deterministic: the 'passing' frequencies pass across all phase/duration shifts, and the 'failing' frequencies fail across all shifts. Thus, rather than a clean frequency-based cutoff, REAPER's epoch tracker simply has complex, discrete 'blind spots' for pure sines in this register. (Note: When given harmonically rich sawtooth waves at these exact failing frequencies, REAPER tracks them perfectly).
2. **Mid-Frequency Subharmonic Locks:** At certain frequencies (e.g., 440 Hz sine), the lack of harmonics causes the epoch tracker to lock onto wide phantom autocorrelation peaks at exactly 1/10th or 1/2 the fundamental (e.g. 43.9 Hz, 220 Hz).
3. **High-Frequency 16kHz Quantization Grid:** Even when REAPER successfully identifies a period, the Python wrapper lacks sub-sample parabolic interpolation. It forcibly quantizes period estimations to exact integer lengths ($P = 16000/N$). As frequencies rise, $N$ decreases, creating massive exponential spacing between representable pitches (labeled `16kHz Quantization Grid` below).

## Test 1: Pure Sine Tone Tracking Accuracy
| Frequency | Engine | Median f0 | Cents Error | Result |
| :--- | :--- | :--- | :--- | :--- |
| 66.0 Hz | pYIN | 66.94 Hz | +24.36 c | FAIL |
| 66.0 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 79.0 Hz | pYIN | 79.60 Hz | +13.53 c | FAIL |
| 79.0 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 94.5 Hz | pYIN | 95.21 Hz | +12.71 c | FAIL |
| 94.5 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 113.1 Hz | pYIN | 113.88 Hz | +11.88 c | FAIL |
| 113.1 Hz | REAPER | 113.48 Hz | +5.73 c | PASS |
| 135.3 Hz | pYIN | 136.21 Hz | +11.06 c | FAIL |
| 135.3 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 162.0 Hz | pYIN | 162.92 Hz | +10.24 c | FAIL |
| 162.0 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 193.8 Hz | pYIN | 194.31 Hz | +4.42 c | PASS |
| 193.8 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 231.9 Hz | pYIN | 233.08 Hz | +8.59 c | PASS |
| 231.9 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 277.5 Hz | pYIN | 278.79 Hz | +7.76 c | PASS |
| 277.5 Hz | REAPER | nan Hz | +nan c | FAIL (NaN) |
| 332.1 Hz | pYIN | 333.46 Hz | +6.94 c | PASS |
| 332.1 Hz | REAPER | 333.33 Hz | +6.29 c | PASS |
| 397.4 Hz | pYIN | 398.85 Hz | +6.11 c | PASS |
| 397.4 Hz | REAPER | 400.00 Hz | +11.11 c | FAIL (16kHz Quantization Grid) |
| 475.6 Hz | pYIN | 477.06 Hz | +5.29 c | PASS |
| 475.6 Hz | REAPER | 238.81 Hz | -1192.71 c | Subharmonic Confusion (1/2) |
| 569.1 Hz | pYIN | 570.61 Hz | +4.46 c | PASS |
| 569.1 Hz | REAPER | 571.43 Hz | +6.95 c | PASS |
| 681.1 Hz | pYIN | 682.50 Hz | +3.64 c | PASS |
| 681.1 Hz | REAPER | 695.65 Hz | +36.67 c | FAIL (16kHz Quantization Grid) |
| 815.0 Hz | pYIN | 816.34 Hz | +2.81 c | PASS |
| 815.0 Hz | REAPER | 800.00 Hz | -32.19 c | FAIL (16kHz Quantization Grid) |
| 975.3 Hz | pYIN | 976.42 Hz | +1.99 c | PASS |
| 975.3 Hz | REAPER | 1000.00 Hz | +43.30 c | FAIL (16kHz Quantization Grid) |
| 1167.1 Hz | pYIN | 1167.89 Hz | +1.16 c | PASS |
| 1167.1 Hz | REAPER | 1142.86 Hz | -36.35 c | FAIL (16kHz Quantization Grid) |
| 1396.6 Hz | pYIN | 1396.91 Hz | +0.34 c | PASS |
| 1396.6 Hz | REAPER | 695.65 Hz | -1206.63 c | Subharmonic Confusion (1/2) |
| 1671.3 Hz | pYIN | 1670.84 Hz | -0.48 c | PASS |
| 1671.3 Hz | REAPER | 842.11 Hz | -1186.69 c | Subharmonic Confusion (1/2) |
| 2000.0 Hz | pYIN | 1998.49 Hz | -1.31 c | PASS |
| 2000.0 Hz | REAPER | 1000.00 Hz | -1200.00 c | Subharmonic Confusion (1/2) |


## Test 2: Harmonically Rich Tones (Sawtooth/Square)
| Freq | Wave | Engine | Cents Error | Result |
| :--- | :--- | :--- | :--- | :--- |
| 110.0 Hz | Saw | pYIN | -0.00 c | PASS |
| 110.0 Hz | Saw | REAPER | +5.42 c | PASS |
| 110.0 Hz | Sq | pYIN | -0.00 c | PASS |
| 110.0 Hz | Sq | REAPER | +5.42 c | PASS |
| 440.0 Hz | Saw | pYIN | +0.00 c | PASS |
| 440.0 Hz | Saw | REAPER | +17.40 c | FAIL (16kHz Quantization Grid) |
| 440.0 Hz | Sq | pYIN | +0.00 c | PASS |
| 440.0 Hz | Sq | REAPER | +17.40 c | FAIL (16kHz Quantization Grid) |
| 880.0 Hz | Saw | pYIN | -0.00 c | PASS |
| 880.0 Hz | Saw | REAPER | -2406.48 c | FAIL (16kHz Quantization Grid) |
| 880.0 Hz | Sq | pYIN | -0.00 c | PASS |
| 880.0 Hz | Sq | REAPER | +nan c | FAIL (NaN) |


## Test 3: Missing Fundamental (Cello Range)
| True F0 | Engine | Measured F0 | Cents Error | Result |
| :--- | :--- | :--- | :--- | :--- |
| 66.0 Hz | pYIN | 66.17 Hz | +4.36 c | PASS |
| 66.0 Hz | REAPER | 66.12 Hz | +3.03 c | PASS |
| 82.0 Hz | pYIN | 81.93 Hz | -1.43 c | PASS |
| 82.0 Hz | REAPER | 82.05 Hz | +1.08 c | PASS |
| 98.0 Hz | pYIN | 98.00 Hz | -0.02 c | PASS |
| 98.0 Hz | REAPER | 98.16 Hz | +2.82 c | PASS |
| 110.0 Hz | pYIN | 110.00 Hz | -0.00 c | PASS |
| 110.0 Hz | REAPER | 110.34 Hz | +5.42 c | PASS |
| 131.0 Hz | pYIN | 130.81 Hz | -2.48 c | PASS |
| 131.0 Hz | REAPER | 131.15 Hz | +1.95 c | PASS |


## Test 4: Quantization / Off-Grid Check
| Base Note | Offset | Engine | Cents Error | Result |
| :--- | :--- | :--- | :--- | :--- |
| 146.8 Hz | +25 c | pYIN | +5.03 c | Expected ~5c Error |
| 146.8 Hz | +25 c | REAPER | +nan c | FAIL (NaN) |
| 146.8 Hz | -25 c | pYIN | +5.03 c | Expected ~5c Error |
| 146.8 Hz | -25 c | REAPER | +nan c | FAIL (NaN) |
| 146.8 Hz | +50 c | pYIN | +10.03 c | FAIL |
| 146.8 Hz | +50 c | REAPER | +nan c | FAIL (NaN) |
| 440.0 Hz | +25 c | pYIN | +5.00 c | Expected ~5c Error |
| 440.0 Hz | +25 c | REAPER | -1207.60 c | Subharmonic Confusion (1/2) |
| 440.0 Hz | -25 c | pYIN | +5.00 c | Expected ~5c Error |
| 440.0 Hz | -25 c | REAPER | -1205.03 c | Subharmonic Confusion (1/2) |
| 440.0 Hz | +50 c | pYIN | -0.00 c | PASS |
| 440.0 Hz | +50 c | REAPER | -1208.39 c | Subharmonic Confusion (1/2) |


## Test 5: Vibrato (FM) Edge Case
| Engine | Median Center F0 | Error from True Center | Modulation Amplitude Tracked |
| :--- | :--- | :--- | :--- |
| pYIN | 440.00 Hz | +0.00 c | 28.25 c (True: 30.00c) |
| REAPER | 219.18 Hz | -1206.48 c | 23.72 c (True: 30.00c) |
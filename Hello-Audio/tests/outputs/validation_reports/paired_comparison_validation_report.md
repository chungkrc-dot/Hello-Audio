# Paired Comparison Validation Report

## 1. Current App Behavior
- **Test 1 (Identical Yield)**: Unplugged N=15, Plugged N=15
  - App delta dBFS: 10.01 dB (Expected ~+10.00 dB)
  - App delta cents: 0.28 cents (Independent Means)

- **Test 3 (Unequal Yield)**: Unplugged N=15, Plugged N=14
  - App delta cents: 1.40 cents (Independent Means)

## 2. Divergence Analysis
This section compares the App's current independent-means calculation vs a simple positional-matched diagnostic subset, derived from a 15-note synthetic sequence with realistic intonation offsets.
- **Identical Yield Gap (Test 1/2)**:
  - App's current delta_cents: 0.28
  - Diagnostic delta_cents: 0.28
  - Absolute Gap: 0.00 cents

- **Asymmetric Yield Gap (Test 3)**:
  - App's current delta_cents: 1.40
  - Diagnostic delta_cents: 0.94
  - Absolute Gap: 0.46 cents

## 3. DTW vs Legacy Structural Difference
- **Test 4 (DTW Harmonic Folding - Octave)**: Using a genuinely synthesized octave error injected into the audio stream and processed via the actual `apply_harmonic_folding` and `calculate_dtw_metrics` pipeline:
  - **Result**: The octave error folded to 20.00 cents.
  - **Correction Tracking**: Correction_Applied=True, Correction_Type='Octave'.
  - **Exclusion**: Note 3 excluded state = True (Expected True despite small deviation).

- **Test 4b (DTW Harmonic Folding - 3rd Harmonic)**: Using a genuinely synthesized +19 semitone error:
  - **Result**: The 3rd harmonic error folded to 0.00 cents.
  - **Correction Tracking**: Correction_Applied=True, Correction_Type='Octave (x2) + Perfect 5th'.
  - **Exclusion**: Note 4 excluded state = True (Expected True despite small deviation).

- **Test 7 (Harmonic Folding Deviation Gate)**: Direct test of the 11.5-semitone minimum-deviation gate.
  - Genuine Octave Error (+12): Residual is 0.0 semitones (Folded correctly).
  - Genuine 3rd Harmonic (+19): Residual is -0.0 semitones (Folded correctly via Perfect 5th band).
  - Major 6th Error (+9): Residual is 9.0 semitones (Unfolded; will correctly fall through to >100c auto-exclude).
  - minor 7th Error (+10): Residual is 10.0 semitones (Unfolded; will correctly fall through to >100c auto-exclude).
  - Major 7th Error (+11): Residual is 11.0 semitones (Unfolded; protected by the new 11.5-semitone gate).

- **Test 5 (Legacy Sequence Misalignment)**:
  - When Note 3 dropped out in the Plugged condition, `zip_longest` structurally misaligned the remaining notes.
  - The resulting DataFrame structure was observed as:
```text
           Detected Sequence (Unplugged) Detected Sequence (Plugged)
Note Index                                                          
1                                     C4                          C4
2                                     D4                          D4
3                                     E4                          F4
4                                     F4                          G4
5                                     G4                          A4
6                                     A4                          B4
7                                     B4                          C5
8                                     C5                          B4
9                                     B4                          A4
10                                    A4                          G4
11                                    G4                          F4
12                                    F4                          E4
13                                    E4                          D4
14                                    D4                          C4
15                                    C4                            
```

## 4. Recommendations for Human Review
- **Option A**: Consider warning the user in the UI when legacy note counts diverge by more than a certain percentage, as this introduces arithmetic drift in the Delta calculation.
- **Option B**: Consider whether Legacy mode needs its own ordinal alignment logic (e.g., Levenshtein distance on note sequences) rather than purely independent means, since it cannot fall back on MIDI anchors.
- **RESOLVED - DTW Harmonic Folding Conflict**: The previous issue where massive tracking errors (octaves/fifths) folded cleanly and bypassed the >100-cent exclusion rule has been fixed. The pipeline now accurately tracks `Correction_Type` and automatically defaults these corrected notes to 'excluded', allowing manual user override.
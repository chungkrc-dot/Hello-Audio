# Hello-Audio

A comparative **intonation and amplitude analysis** engine for solo string performance.
Upload a recording (and optionally the score as MIDI) and the app reports how far each
played note deviates from its target pitch, in cents, together with the full deviation
distribution and a loudness profile.

Two pitch trackers are supported and can be swapped from the sidebar:

| Engine | Family | Notes |
| :--- | :--- | :--- |
| **pYIN** (default) | Probabilistic YIN, HMM-based | Graded voicing confidence; quantizes f0 onto a ~5-cent lattice |
| **REAPER** | Epoch-based | Binary voicing flag; finer pitch resolution, prone to octave folding |

When a MIDI score is supplied, notes are matched to the score by **Dynamic Time Warping**
rather than by the legacy "locked target" nearest-note rule, which makes the analysis
robust to rubato and tempo drift.

The algorithms, their parameters, and the empirical validation behind them are documented
in [docs/technical_manual.md](docs/technical_manual.md).

---

## Requirements

- **Python 3.9** (pinned dependency set is verified against 3.9.6, macOS/arm64)
- A **C/C++ toolchain** — `pyreaper` has no wheel and builds from an sdist.
  On macOS: `xcode-select --install`

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` is fully pinned. Re-pin only after re-running the test suite.

> **Note on `pyreaper`:** it is imported lazily at
> [src/pitch_engine.py:41](src/pitch_engine.py#L41), inside the `pitch_engine == "REAPER"`
> branch. A venv missing it will pass every test and start the app normally, then crash the
> first time someone selects REAPER in a demo. Verify it explicitly:
>
> ```bash
> python -c "import pyreaper; print('pyreaper OK')"
> ```

## Running the app

```bash
streamlit run app/app.py
```

Then open http://localhost:8501.

Run it from the **repository root** — `app/app.py` imports `ui_components` as a top-level
module, which resolves only because Streamlit puts the script's own directory on `sys.path`.

## Running the tests

```bash
python -m pytest -q
```

Expected: **69 passed**.

Collection is scoped by [pytest.ini](pytest.ini) to the suites directly under `tests/`.
Everything below `tests/scripts/` is a set of argparse CLI tools, not pytest suites; several
define a helper named `test_condition()` that pytest would otherwise try to collect and fail
on. Do not remove that scoping without renaming those helpers.

---

## Repository layout

```
app/                  Streamlit UI (app.py orchestrator, ui_components.py widgets/tables)
src/                  Analysis library
  pitch_engine.py       pYIN / REAPER extraction, filtering, legacy intonation scoring
  midi_parser.py        MIDI note + timing extraction (hand-rolled chunk parser, no MIDI library)
  midi_alignment.py     DTW alignment, harmonic folding, DTW-mode metrics
  amplitude_analysis.py RMS / perceptual loudness
  stats_summary.py      Descriptive stats, Bland-Altman, quantization diagnostics
  visualization.py      Pitch-track plots
scripts/              Standalone utilities (headless.py = full CLI analyzer)
tests/                pytest suites (69 tests)
  scripts/batch/        Corpus batch runners (Appendix A, sigma-2, DTW mode comparison)
  scripts/validation/   Validation studies + their committed .md/.json reports
  scripts/unit/         Ad-hoc CLI proof scripts (not pytest)
  scripts/reports/      Certification figure generation
  outputs/              Generated artifacts (gitignored except certification_reports/)
docs/                 technical_manual.md and its figures
```

## Headless analysis

For scripted runs without the UI:

```bash
python scripts/headless.py <audio.wav> <score.mid> {Violin|Viola|Cello}
```

Parameters default to the UI values; see `--help` for the filter thresholds and the
bypass toggles used in the failure-mode studies.

## Batch and validation runs

```bash
./run_batch.sh                                      # Appendix A corpus batch
python tests/scripts/validation/validate_pitch_accuracy.py
```

These read the URMP-derived corpus in `dataset (Strings only)/`, which is **gitignored** and
not present in a fresh clone — the batch scripts need it supplied separately. Their committed
reports under `tests/scripts/validation/` are tracked deliberately, because the technical
manual cites them.

## Engine optimal defaults

The defaults below produced every empirical result in the technical manual. The sidebar's
three tempo profiles are a Legacy-mode convenience and are **not** that configuration.

| Parameter | Default |
| :--- | :--- |
| Pitch tracker | pYIN |
| Reference pitch | 440.0 Hz |
| Switch probability (β) | 0.005 |
| RMS amplitude threshold | 0.005 |
| Minimum sustain duration | 2 frames (pYIN) / 4 frames (REAPER) |
| Maximum pitch slope | 0.50 semitones/frame |
| Voicing confidence threshold | 0.0 (off) |

> **Reading the statistics:** on pYIN data the order statistics (median, Q1/Q3, IQR, MAD) are
> constrained to the ~5-cent output lattice and should be read as naming a cell, not as
> measurements. The **10%-trimmed mean** is the recommended robust single figure. See §9 and
> Appendix J of the technical manual.

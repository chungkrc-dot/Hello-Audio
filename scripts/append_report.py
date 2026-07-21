import re

# Read the markdown table
with open('/Users/conradchung/.gemini/antigravity/brain/144bb055-59e2-4a86-9b79-cd054e17846b/all_strings_reaper_batch_results.md', 'r') as f:
    md_content = f.read()

# Extract just the table rows
table_lines = []
in_table = False
for line in md_content.split('\n'):
    if line.startswith('| Dataset'):
        in_table = True
        # skip header
        continue
    if in_table and line.startswith('|---'):
        continue
    if in_table and line.strip() == '':
        in_table = False
    if in_table:
        table_lines.append(line)

table_str = "\n".join(table_lines)

report = f"""

## 11. Appendix A: URMP Batch Test Results

This section details the results of a comprehensive batch test conducted on the University of Rochester Multi-Modal Music Performance (URMP) dataset to evaluate the performance of the REAPER pitch tracking engine on bowed string instruments.

### Testing Methodology
* **Dataset**: URMP (University of Rochester Multi-Modal Music Performance) dataset.
* **Algorithm**: Robust Epoch And Pitch EstimatoR (REAPER) paired with Dynamic Time Warping (DTW).
* **Sample Length**: Full, un-truncated audio samples for all pieces were analyzed to ensure robust real-world evaluation against extended musical performances.
* **Pieces Tested**: Classical ensemble recordings ranging from duets to quintets, including Mozart, Vivaldi, Bach, and others.
* **Parts Tested**: Violin (vn), Viola (va), and Cello (vc) stems.

### Overall Detection Yield (By Instrument)
The detection yield measures the system's ability to successfully track and isolate physical notes compared to the ground-truth MIDI score. 

| Instrument | Total Notes Expected | Total Notes Detected | Detection Yield (%) |
| :--- | :---: | :---: | :---: |
| **Violin** | 7,667 | 7,222 | 94.20% |
| **Viola** | 2,964 | 2,808 | 94.74% |
| **Cello** | 2,344 | 2,275 | 97.06% |
| **Total** | **12,975** | **12,305** | **94.84%** |

### Mean Intonation Deviation (By Instrument)
The following table summarizes the mean frequency deviation (in Hz) between the tracked physical acoustic performance and the target pitch.

| Instrument | Mean Deviation (Hz) |
| :--- | :---: |
| **Violin** | +3.57 Hz |
| **Viola** | +0.11 Hz |
| **Cello** | +0.93 Hz |

*(Note: Minor positive deviations may reflect standard acoustic tuning tendencies, such as string players naturally playing slightly sharp during expressive passages).*

### Detailed Track Results
The following table provides the exhaustive breakdown of the detection yield and intonation deviation for each individual audio track analyzed in the batch test.

| Dataset Piece | Part | Instrument | Notes Detected | Notes Expected | Yield (%) | Mean Deviation (Hz) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
{table_str}
"""

with open('/Users/conradchung/Documents/PythonCode/Hello-Audio/docs/technical_manual.md', 'a') as f:
    f.write(report)

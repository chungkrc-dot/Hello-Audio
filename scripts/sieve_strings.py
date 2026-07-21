import os
import shutil
import re

source_dir = 'dataset'
dest_dir = 'dataset (Strings only)'
summary_file = 'string_instruments_summary.txt'

if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)

instruments_to_find = {'vn': 'Violin', 'va': 'Viola', 'vc': 'Cello'}

total_counts = {'vn': 0, 'va': 0, 'vc': 0}
piece_counts = {}

# Regex to match URMP piece folders (e.g. 01_Jupiter_vn_vc)
piece_pattern = re.compile(r'^\d{2}_')

for piece_folder in sorted(os.listdir(source_dir)):
    piece_path = os.path.join(source_dir, piece_folder)
    
    if os.path.isdir(piece_path) and piece_pattern.match(piece_folder):
        piece_counts[piece_folder] = {'vn': 0, 'va': 0, 'vc': 0}
        
        for part_folder in sorted(os.listdir(piece_path)):
            part_path = os.path.join(piece_path, part_folder)
            
            if os.path.isdir(part_path):
                # part folders are typically like "1_vn", "2_vc"
                suffix = part_folder.split('_')[-1]
                
                if suffix in instruments_to_find:
                    total_counts[suffix] += 1
                    piece_counts[piece_folder][suffix] += 1
                    
                    # Create destination structure
                    dest_piece_path = os.path.join(dest_dir, piece_folder, part_folder)
                    os.makedirs(dest_piece_path, exist_ok=True)
                    
                    # Copy .wav and .mid files
                    for file in os.listdir(part_path):
                        if file.endswith('.wav') or file.endswith('.mid'):
                            src_file = os.path.join(part_path, file)
                            dst_file = os.path.join(dest_piece_path, file)
                            shutil.copy2(src_file, dst_file)

# Generate summary text file
with open(summary_file, 'w') as f:
    f.write("URMP String Instruments Summary\n")
    f.write("===============================\n\n")
    
    f.write("Total counts across all pieces:\n")
    f.write("-------------------------------\n")
    f.write(f"Violin (vn): {total_counts['vn']}\n")
    f.write(f"Viola (va):  {total_counts['va']}\n")
    f.write(f"Cello (vc):  {total_counts['vc']}\n")
    f.write(f"Total:       {sum(total_counts.values())}\n\n")
    
    f.write("Counts per piece:\n")
    f.write("-----------------\n")
    for piece, counts in piece_counts.items():
        total_in_piece = sum(counts.values())
        if total_in_piece > 0:
            f.write(f"{piece}:\n")
            f.write(f"  Violins: {counts['vn']}\n")
            f.write(f"  Violas:  {counts['va']}\n")
            f.write(f"  Cellos:  {counts['vc']}\n")
            f.write(f"  Total string parts: {total_in_piece}\n\n")

print(f"Extraction complete. Copied {sum(total_counts.values())} string parts to '{dest_dir}'.")
print(f"Summary written to '{summary_file}'.")

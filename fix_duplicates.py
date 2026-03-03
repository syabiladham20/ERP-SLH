import re

files_to_modify = [
    'templates/flock_detail.html',
    'templates/flock_detail_readonly.html',
    'templates/flock_detail_modern.html'
]

for filename in files_to_modify:
    with open(filename, 'r') as f:
        content = f.read()

    # Find the first occurrence of // --- Floating Notes Logic ---
    first_idx = content.find("// --- Floating Notes Logic ---")

    if first_idx != -1:
        # Check if there is a second occurrence
        second_idx = content.find("// --- Floating Notes Logic ---", first_idx + 1)
        if second_idx != -1:
            # We have duplicates.
            # Remove from first_idx to end of script, and keep only one copy.
            # It's safer to just split by // --- Floating Notes Logic ---
            parts = content.split("// --- Floating Notes Logic ---")

            # The first part is the content before the logic
            # The last part is the logic and the rest of the file
            # But wait, there are 3 parts if there are 2 occurrences.
            # Let's clean up manually with regex

            clean_content = re.sub(r'// --- Floating Notes Logic ---.*?(?=// --- Floating Notes Logic ---)', '', content, flags=re.DOTALL)

            # This leaves one occurrence.

            with open(filename, 'w') as f:
                f.write(clean_content)
            print(f"Fixed {filename}")

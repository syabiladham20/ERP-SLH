import pandas as pd

# Read first 10 rows without header
df = pd.read_excel('template.xlsx', header=None, nrows=10)

print("Analyzing Metadata Rows:")
for idx, row in df.iterrows():
    first_col = str(row[0])
    if "HOUSE" in first_col or "INTAKE" in first_col:
        # Find first non-null column after 0
        for col_idx in range(1, len(row)):
            val = row[col_idx]
            if pd.notna(val):
                print(f"Row {idx}: Label='{first_col}', Value Found at Col {col_idx}: '{val}'")
                break

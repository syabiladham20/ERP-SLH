import pandas as pd

df = pd.read_excel('slh_daily.xlsx', sheet_name='VA2', header=None, nrows=10)
print("Metadata Check for Sheet 'VA2':")
for r in range(1, 5):
    print(f"Row {r}: {df.iloc[r, :5].tolist()}")

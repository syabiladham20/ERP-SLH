import pandas as pd
import openpyxl

wb = openpyxl.load_workbook('slh_daily.xlsx', read_only=True)
print("Sheet Names:", wb.sheetnames)

df = pd.read_excel('slh_daily.xlsx', header=None, nrows=10)
print("\nMetadata Search:")
for r in range(1, 5):
    row_vals = df.iloc[r].tolist()
    print(f"Row {r}: {row_vals[:10]}")

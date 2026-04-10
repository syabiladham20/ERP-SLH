import pandas as pd

# Read rows around 506 to check weekly data
# Row 506 (1-based) is index 505.
df = pd.read_excel('template.xlsx', header=None, skiprows=504, nrows=10)
print(df)

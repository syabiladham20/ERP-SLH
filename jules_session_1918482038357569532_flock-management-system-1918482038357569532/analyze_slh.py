import pandas as pd

# Analyze the new file structure
print("Reading slh_daily.xlsx headers...")
try:
    df_head = pd.read_excel('slh_daily.xlsx', header=None, nrows=15)
    print(df_head)
    
    # Check if header is at row 9 (index 8) like before
    print("\nRow 9 values:")
    print(df_head.iloc[8].tolist())
    
    # Check Metadata location
    print("\nMetadata check:")
    print("B2:", df_head.iloc[1, 1])
    print("B3:", df_head.iloc[2, 1])
    print("B4:", df_head.iloc[3, 1])
    print("B5:", df_head.iloc[4, 1])
    
except Exception as e:
    print(f"Error: {e}")

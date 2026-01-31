import pandas as pd
import os

def analyze_template():
    try:
        # Construct path relative to repo root (assuming script run from root)
        path = 'jules_session_1918482038357569532_flock-management-system-1918482038357569532/template.xlsx'
        print(f"Reading: {path}")
        xls = pd.ExcelFile(path)
        print(f"Sheets: {xls.sheet_names}")
<<<<<<< HEAD
<<<<<<< HEAD

        sheet = xls.sheet_names[0]
        print(f"Analyzing Sheet: {sheet}")

        # Read header=None to get raw rows
        df = pd.read_excel(xls, sheet_name=sheet, header=None)

=======
=======
>>>>>>> origin/import-logic-fix-704397853420473837

        sheet = xls.sheet_names[0]
        print(f"Analyzing Sheet: {sheet}")

        # Read header=None to get raw rows
        df = pd.read_excel(xls, sheet_name=sheet, header=None)

<<<<<<< HEAD
=======
=======

        sheet = xls.sheet_names[0]
        print(f"Analyzing Sheet: {sheet}")

        # Read header=None to get raw rows
        df = pd.read_excel(xls, sheet_name=sheet, header=None)

>>>>>>> origin/import-logic-fix-704397853420473837
>>>>>>> origin/import-logic-fix-704397853420473837
        print("\n--- Daily Header (Row 9 / Index 8) ---")
        row_8 = df.iloc[8]
        for idx, val in enumerate(row_8):
            if pd.notna(val):
                print(f"Col {idx}: {val}")
<<<<<<< HEAD
<<<<<<< HEAD

=======

=======

=======

>>>>>>> origin/import-logic-fix-704397853420473837
>>>>>>> origin/import-logic-fix-704397853420473837
        # Look for new male fields in header
        # specifically "Hospital", "Transfer" etc.

        print("\n--- Weekly Header (Row 506 / Index 505) ---")
        if len(df) > 505:
            row_505 = df.iloc[505]
            for idx, val in enumerate(row_505):
                if pd.notna(val):
                    print(f"Col {idx}: {val}")
        else:
            print("Row 506 not found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_template()

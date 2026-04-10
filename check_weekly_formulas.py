import openpyxl

wb = openpyxl.load_workbook('template.xlsx', data_only=False)
sheet = wb.active

# Row 508 is Week 1 data
row_idx = 509 # 1-based index for row 509 (index 508 in pandas) - wait, pandas said row 3 is data. 
# Pandas read from 504.
# 0: 504
# 1: 505 (Header) -> Row 506 in Excel?
# 2: 506 (NaN)
# 3: 507 (Week 1) -> Row 508 in Excel.

# Let's check Row 509 in openpyxl (which is row 509).
# User said "data from row 508".
row_idx = 508

headers = [cell.value for cell in sheet[506]] # Header at 506

row_cells = sheet[row_idx]
for i, cell in enumerate(row_cells):
    header_name = headers[i] if i < len(headers) else "Unknown"
    has_formula = (cell.data_type == 'f')
    
    if has_formula:
        print(f"Column {cell.column_letter} ({header_name}) has formula: {cell.value}")

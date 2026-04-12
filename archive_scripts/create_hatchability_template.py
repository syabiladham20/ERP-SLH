import openpyxl
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, LineChart, Reference, Series
from openpyxl.chart.axis import TextAxis
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

def create_template():
    wb = Workbook()

    # --- Sheet 1: Flock Reference ---
    ws_ref = wb.active
    ws_ref.title = "Flock Reference"

    headers_ref = ["Flock ID", "Intake Date"]
    ws_ref.append(headers_ref)

    # Styling Header
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")

    for cell in ws_ref[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Add some sample data instructions or blank rows
    ws_ref["A2"] = "Example_Flock_01"
    ws_ref["B2"] = "2023-01-01"
    ws_ref.column_dimensions["A"].width = 25
    ws_ref.column_dimensions["B"].width = 15

    # --- Sheet 2: Data ---
    ws_data = wb.create_sheet("Data")

    headers_data = [
        "Setting Date",       # A
        "Candling Date",      # B
        "Hatching Date",      # C
        "Flock ID",           # D
        "Egg Set",            # E
        "Clear Egg",          # F
        "Clear Egg %",        # G (Calc)
        "Rotten Egg",         # H
        "Rotten Egg %",       # I (Calc)
        "Hatchable Egg",      # J (Calc: E - F - H) -> Fertile
        "Hatchable Egg %",    # K (Calc: J / E)
        "Total Hatched",      # L
        "Hatchability %",     # M (Calc: L / E) -> Hatch of Total
        "Male Ratio %",       # N (Input)
        "Flock Age (Weeks)"   # O (Calc for Graph)
    ]

    ws_data.append(headers_data)

    # Style Header
    for cell in ws_data[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Column Widths
    ws_data.column_dimensions['A'].width = 12
    ws_data.column_dimensions['B'].width = 12
    ws_data.column_dimensions['C'].width = 12
    ws_data.column_dimensions['D'].width = 20
    ws_data.column_dimensions['E'].width = 10
    ws_data.column_dimensions['F'].width = 10
    ws_data.column_dimensions['G'].width = 12
    ws_data.column_dimensions['H'].width = 10
    ws_data.column_dimensions['I'].width = 12
    ws_data.column_dimensions['J'].width = 12
    ws_data.column_dimensions['K'].width = 15
    ws_data.column_dimensions['L'].width = 12
    ws_data.column_dimensions['M'].width = 15
    ws_data.column_dimensions['N'].width = 12
    ws_data.column_dimensions['O'].width = 15

    # Define Formulas for Rows 2 to 500
    for row in range(2, 102): # Pre-populate 100 rows
        # G: Clear % = F/E
        ws_data[f"G{row}"] = f"=IF(E{row}>0, F{row}/E{row}, 0)"

        # I: Rotten % = H/E
        ws_data[f"I{row}"] = f"=IF(E{row}>0, H{row}/E{row}, 0)"

        # J: Hatchable (Fertile) = E - F - H
        ws_data[f"J{row}"] = f"=IF(E{row}>0, E{row}-F{row}-H{row}, 0)"

        # K: Hatchable % (Fertility %) = J/E
        ws_data[f"K{row}"] = f"=IF(E{row}>0, J{row}/E{row}, 0)"

        # M: Hatchability % (Hatch of Total) = L/E
        ws_data[f"M{row}"] = f"=IF(E{row}>0, L{row}/E{row}, 0)"

        # O: Age = INT((SettingDate - 1 - Intake)/7)
        # Using IFERROR to handle missing Flock ID or Dates
        # Lookup refers to Sheet 'Flock Reference' cols A:B
        ws_data[f"O{row}"] = f"=IFERROR(INT((A{row}-1-VLOOKUP(D{row},'Flock Reference'!$A:$B,2,FALSE))/7), \"\")"

        # Apply Percentage Format
        for col in ['G', 'I', 'K', 'M', 'N']:
            ws_data[f"{col}{row}"].number_format = '0.00%'

    # --- Chart Generation ---
    # We create a Dynamic Chart or just reference the first 100 rows?
    # Usually safer to reference a fixed range or named range.
    # For this template, I'll reference A1:O101 (Header + 100 rows data).
    # User can extend the range in Excel if needed.

    # Chart Data:
    # Categories (X): Column O (Flock Age)
    # Primary Axis (Stacked Bar): Hatchable/Fertile % (K), Clear % (G), Rotten % (I)
    # Secondary Axis (Line): Hatchability % (M)

    # Create the Bar Chart (Primary) - Stacked
    c1 = BarChart()
    c1.type = "col"
    c1.style = 10
    c1.grouping = "stacked"
    c1.overlap = 100
    c1.title = "Hatchability Analysis"
    c1.y_axis.title = "Egg Composition (%)"
    c1.x_axis.title = "Flock Age (Weeks)"

    # Force Text Axis to ensure duplicate categories (e.g. same week for diff setters) are plotted separately
    c1.x_axis = TextAxis()
    c1.x_axis.title = "Flock Age (Weeks)"

    # Data for Bar Chart
    # K (Hatchable/Fertile %), G (Clear), I (Rotten)
    # Column indices (1-based):
    # G = 7
    # I = 9
    # K = 11
    # M = 13
    # N = 14 (Male Ratio - removed from graph)
    # O = 15

    data_fertile = Reference(ws_data, min_col=11, min_row=1, max_row=101) # K
    data_clear = Reference(ws_data, min_col=7, min_row=1, max_row=101)    # G
    data_rotten = Reference(ws_data, min_col=9, min_row=1, max_row=101)   # I

    c1.add_data(data_fertile, titles_from_data=True)
    c1.add_data(data_clear, titles_from_data=True)
    c1.add_data(data_rotten, titles_from_data=True)

    # Set Categories (X Axis) -> Column O
    cats = Reference(ws_data, min_col=15, min_row=2, max_row=101)
    c1.set_categories(cats)

    # Create the Line Chart (Secondary)
    c2 = LineChart()
    c2.style = 13
    c2.y_axis.title = "Hatchability %"
    c2.y_axis.axId = 200
    c2.y_axis.crosses = "max"

    # Secondary Data: Hatchability % (M)
    data_hatchability = Reference(ws_data, min_col=13, min_row=1, max_row=101) # M
    c2.add_data(data_hatchability, titles_from_data=True)

    # Combine
    c1 += c2

    # Size and Position
    c1.height = 15 # cm approx
    c1.width = 30

    ws_data.add_chart(c1, "Q2")

    # Save
    wb.save("Hatchability_Template.xlsx")
    print("Template created: Hatchability_Template.xlsx")

if __name__ == "__main__":
    create_template()

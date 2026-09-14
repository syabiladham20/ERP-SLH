import openpyxl
import datetime

wb = openpyxl.load_workbook('PPSB_PCHS_2026_Stock Report_Raw Material & Woven Bag_Harumi.xlsx', data_only=True)

# 1. Ingredients
ws_formula = wb['FORMULA']
ws_sum = wb['SUMMARY']
ws_jan = wb['Jan26']

ingredients = []
ing_seen = set()

# From FORMULA
for r in range(6, ws_formula.max_row+1):
    val = ws_formula.cell(r, 1).value
    if val and isinstance(val, str):
        v = val.strip()
        if v not in ing_seen and not any(v.startswith(p) for p in ['1101', '1102', '1103', '1104', '8100', '121', '122', '123', 'PREMIX', 'TOP UP', 'WOVEN BAG', 'FORMULA', 'ADDITIVE']):
            ing_seen.add(v)
            ingredients.append(v)

# From SUMMARY
for c in range(2, ws_sum.max_column+1):
    val = ws_sum.cell(3, c).value
    if val and isinstance(val, str):
        v = val.strip()
        if v not in ing_seen:
            ing_seen.add(v)
            ingredients.append(v)

# From Jan26
for r in range(4, 50):
    val = ws_jan.cell(r, 2).value
    if val and isinstance(val, str):
        v = val.strip()
        if v not in ing_seen and v not in ['RAW MATERIAL', 'WOVEN BAG', 'MEDICINE', 'PACKAGING', 'TOTAL']:
            ing_seen.add(v)
            ingredients.append(v)

print(f"Master Ingredients count: {len(ingredients)}")

# 2. Formulations extraction
formulations = []
feed_master_dict = {
    '1101C': {'name': 'Broiler Starter 1101C', 'batch_size': 1.0},
    '1102C/P': {'name': 'Broiler Grower 1102C/P', 'batch_size': 1.0},
    '1103P': {'name': 'Broiler Finisher 1 1103P', 'batch_size': 1.0},
    '1104P': {'name': 'Broiler Finisher 2 1104P', 'batch_size': 1.0},
    '8100': {'name': 'Broiler Pre-Starter 8100', 'batch_size': 1.0},
    '8101': {'name': 'Broiler Starter 8101', 'batch_size': 1.0},
    '8102': {'name': 'Broiler Grower 8102', 'batch_size': 1.0},
    '8103': {'name': 'Broiler Finisher 8103', 'batch_size': 1.0},
    '121': {'name': 'Broiler Starter 121', 'batch_size': 1.0},
    '122': {'name': 'Broiler Grower 122', 'batch_size': 1.0},
    '123': {'name': 'Broiler Finisher 123', 'batch_size': 1.0},
}

# Inspect columns in FORMULA sheet for WS spec codes
col_formulas = []

for c in range(2, ws_formula.max_column+1):
    r2_val = ws_formula.cell(2, c).value
    r3_val = ws_formula.cell(3, c).value
    r4_val = ws_formula.cell(4, c).value
    r5_val = ws_formula.cell(5, c).value

    spec_code = r3_val or r4_val
    if spec_code and isinstance(spec_code, str) and (spec_code.startswith('WS') or spec_code.startswith('YH') or spec_code.startswith('31') or spec_code.startswith('52')):
        # Deduce Feed Code from spec_code or nearby header
        feed_code = '1101C'
        if '1101' in spec_code: feed_code = '1101C'
        elif '1102' in spec_code: feed_code = '1102C/P'
        elif '1103' in spec_code: feed_code = '1103P'
        elif '1104' in spec_code: feed_code = '1104P'
        elif '8100' in spec_code: feed_code = '8100'
        elif '8101' in spec_code: feed_code = '8101'
        elif '8102' in spec_code: feed_code = '8102'
        elif '8103' in spec_code: feed_code = '8103'
        elif '121' in spec_code or '311' in spec_code or '312' in spec_code: feed_code = '121'
        elif '122' in spec_code or '5201' in spec_code or '5202' in spec_code: feed_code = '122'
        elif '123' in spec_code: feed_code = '123'

        col_formulas.append({
            'col': c,
            'feed_code': feed_code,
            'spec_code': spec_code.strip(),
            'unit_type': r5_val
        })

print(f"Found {len(col_formulas)} formula specs in FORMULA sheet.")
for cf in col_formulas[:10]:
    print(cf)

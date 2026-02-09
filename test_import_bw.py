import unittest
from app import app, db, House, Flock, DailyLog
import pandas as pd
import io
from datetime import date, datetime

class ImportStandardBWTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def create_excel_file(self):
        # Create Excel file structure
        # 0-9: Metadata
        meta_data = [
            ["", ""],
            ["HOUSE:", "TEST_HOUSE_BW"],
            ["FEMALE INTAKE:", 100],
            ["MALE INTAKE:", 100],
            ["INTAKE DATE:", "2023-01-01"],
            ["", ""], ["", ""], ["", ""], ["", ""], ["", ""]
        ]

        # 10-507: Data Rows (Padding)
        # We need rows for Week 1 (Day 7 -> 2023-01-08) and Week 3 (Day 21 -> 2023-01-22)
        # Row 10 corresponds to Day 1? usually row 11 (index 10) is first data row.
        # Let's just fill rows with empty strings except for our target dates.

        # Header (Row 9, Index 8)
        header = [""] * 60
        header[1] = "DATE"
        header[39] = "BW Male" # Index 39
        header[41] = "BW Female" # Index 41

        rows = []
        # Pad Metadata to 60 cols
        for m in meta_data:
            rows.append(m + [""] * (60 - len(m)))

        # Add Header? process_import reads header=8 (Row 9).
        # We have 10 metadata rows (0-9).
        # Wait, process_import:
        # df_meta = read_excel(..., nrows=10) -> Reads rows 0-9.
        # df_data = read_excel(..., header=8) -> Header is Row 9 (Index 8).
        # So Row 0-8 are skipped/header. Row 9 (Index 9) is first data row?
        # Actually header=8 means 0-based index 8 is header. (Row 9 in Excel).
        # Data starts from Index 9 (Row 10).

        # We need to construct the list carefully.
        # Index 0-7: Metadata/Padding
        # Index 8: Header
        # Index 9+: Data

        # Let's reconstruct based on list index:
        sheet_data = []

        # 0-7 (8 rows): Metadata
        for i in range(8):
            if i < len(meta_data):
                sheet_data.append(meta_data[i] + [""] * (60 - len(meta_data[i])))
            else:
                sheet_data.append([""] * 60)

        # 8: Header
        sheet_data.append(header)

        # 9-506: Data Rows (Indices 9 to 506)
        # We want Day 7 (2023-01-08) and Day 21 (2023-01-22)
        # Intake is 2023-01-01 (Day 0/1?).
        # App logic: days_diff = (date - intake).days. Week = (diff // 7) + 1.
        # 2023-01-08 - 2023-01-01 = 7 days. 7 // 7 = 1. Week 2?
        # Wait: 0-6 days = Week 1. 7-13 days = Week 2.
        # Let's check: (7 // 7) + 1 = 2.
        # So 2023-01-08 is Week 2.
        # We want Week 1 standard?
        # Week 1: 0 days diff? 2023-01-01.
        # Let's use Week 5 and Week 10 to be safe and clear.
        # Week 5: (5-1)*7 = 28 days. Date = 2023-01-01 + 28 days = 2023-01-29.
        # Week 10: (10-1)*7 = 63 days. Date = 2023-01-01 + 63 days = 2023-03-05.

        # Create a map of Date -> Data
        date_map = {
            "2023-01-29": (5, 100, 100), # Week 5, BW M, BW F
            "2023-03-05": (10, 200, 200) # Week 10
        }

        # Fill data rows up to index 506
        # We need to reach row 507 for Standard BW start.
        # So we need 508 rows total (0-507).
        current_row = 9
        while current_row < 507:
            row = [""] * 60
            # Just put dates for our targets
            if current_row == 40: # Arbitrary position for Week 5
                row[1] = "2023-01-29"
                row[39] = 100 # Male BW P1
                row[41] = 100 # Female BW P1
                row[40] = 1 # Uniformity
                row[42] = 1
            elif current_row == 80: # Arbitrary position for Week 10
                row[1] = "2023-03-05"
                row[39] = 200
                row[41] = 200
                row[40] = 1
                row[42] = 1

            sheet_data.append(row)
            current_row += 1

        # Index 507: Start of Standard BW (Row 508)
        # Structure: Col 0 (Week), Col 32 (Male Std), Col 33 (Female Std)

        # Row 507: Week 0
        # ...
        # We need Week 5 (Target 1 - Valid)
        # We need Week 10 (Target 2 - Invalid)

        # Let's fill 70 rows of standards
        for i in range(70):
            row = [""] * 60
            week_num = i
            row[0] = week_num

            if week_num == 5:
                # Valid Data
                row[32] = 50.5 # Male Std
                row[33] = 45.5 # Female Std
            elif week_num == 10:
                # Invalid Data (Missing or String)
                row[32] = "invalid"
                row[33] = 90.0
            else:
                row[32] = 10 + i
                row[33] = 10 + i

            sheet_data.append(row)

        # Convert to DataFrame
        df = pd.DataFrame(sheet_data)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, header=False)
        output.seek(0)
        return output

    def test_import_standard_bw(self):
        excel_file = self.create_excel_file()

        # Post to import
        response = self.app.post('/import', data={
            'files': (excel_file, 'test_bw.xlsx')
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertIn(b'Successfully imported 1 files.', response.data)

        # Verify Database
        # Check Week 5 (2023-01-29)
        # Intake 2023-01-01. 2023-01-29 is +28 days.
        # Week = (28 // 7) + 1 = 5.

        house = House.query.filter_by(name='TEST_HOUSE_BW').first()
        flock = Flock.query.filter_by(house_id=house.id).first()

        log_w5 = DailyLog.query.filter_by(flock_id=flock.id, date=date(2023, 1, 29)).first()
        self.assertIsNotNone(log_w5)
        # Check Standard BW
        # We set Week 5 Std Male = 50.5, Female = 45.5
        self.assertEqual(log_w5.standard_bw_male, 50.5)
        self.assertEqual(log_w5.standard_bw_female, 45.5)

        # Check Week 10 (2023-03-05)
        # We set Week 10 Std Male = "invalid"
        # Current behavior: try/except block catches "int('invalid')" or "float('invalid')" and continues loop.
        # So Week 10 is NOT added to standard_bw_map.
        # Log logic: if week_num in map: set std. Else: do nothing (default 0).

        log_w10 = DailyLog.query.filter_by(flock_id=flock.id, date=date(2023, 3, 5)).first()
        self.assertIsNotNone(log_w10)
        self.assertEqual(log_w10.standard_bw_male, 0.0) # Default

        # Check for Flash Messages
        # We expect a warning for Week 10 because standard data was invalid ("invalid")
        # Flash message: "Warning: Standard BW data invalid for weeks: 10..."
        self.assertIn(b'Standard BW data invalid for weeks: 10', response.data)

if __name__ == '__main__':
    unittest.main()

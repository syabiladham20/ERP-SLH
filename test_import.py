import unittest
from app import app, db, House, Flock, DailyLog
import pandas as pd
import os
import io
from datetime import date, datetime

class ImportTestCase(unittest.TestCase):
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

    def test_import_logic(self):
        # Create a mock Excel file using pandas
        # Metadata
        # Row 1 (Index 1) Col 1 (B): House Name
        # ...
        
        # We need to construct the dataframe to match process_import expectations
        # It expects 10 metadata rows first
        meta_data = [
            ["", ""], # 0
            ["HOUSE:", "TEST_HOUSE_1"], # 1 (B2)
            ["FEMALE INTAKE:", 100], # 2 (B3)
            ["MALE INTAKE:", 100], # 3 (B4)
            ["INTAKE DATE:", "2023-01-01"], # 4 (B5)
            ["", ""], ["", ""], ["", ""], ["", ""], ["", ""] # Padding
        ]
        df_meta = pd.DataFrame(meta_data)
        
        # Data rows
        # Header at Row 9 (Index 8), Data starts Row 10 (Index 9)
        # We need a DataFrame that when read with header=8, returns correct columns
        # Index 8 is header.
        
        # Create data dictionary matching columns by index
        # A(0)..BE(56)
        data = {}
        for i in range(60):
            data[i] = [None, None]
            
        # Add 2 days of data
        # Day 1: 2023-01-01
        data[1][0] = "2023-01-01" # Date
        data[2][0] = 1 # Cull Male
        data[43][0] = 10000 # Water 1
        data[56][0] = "Note1"
        
        # Day 2: 2023-01-02
        data[1][1] = "2023-01-02"
        data[2][1] = 2 # Cull Male
        data[43][1] = 10500 # Water 1
        data[56][1] = "Note2"
        
        df_data = pd.DataFrame(data)
        
        # Combine: We need to write this to an Excel buffer
        # But wait, `process_import` reads `header=None` for metadata, then `header=8` for data.
        # So we need to construct a single Excel sheet.
        
        # Let's build a list of lists representing the sheet
        sheet_data = []
        # 0-8: Metadata (9 rows)
        for i in range(9):
            if i < len(meta_data):
                # Ensure metadata rows are also wide enough
                row_padding = [""] * (60 - len(meta_data[i]))
                sheet_data.append(meta_data[i] + row_padding)
            else:
                sheet_data.append([""]*60)
                
        # Row 9 (Index 8): Header
        header_row = [""]*60
        header_row[1] = "DATE"
        header_row[56] = "REMARKS" # Force width
        sheet_data.append(header_row)
        
        # Row 10+: Data
        # Day 1
        row1 = [""]*60
        row1[1] = "2023-01-01"
        row1[2] = 1
        row1[43] = 10000
        row1[56] = "Note1"
        sheet_data.append(row1)
        
        # Day 2
        row2 = [""]*60
        row2[1] = "2023-01-02"
        row2[2] = 2
        row2[43] = 10500
        row2[56] = "Note2"
        sheet_data.append(row2)
        
        df_final = pd.DataFrame(sheet_data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, header=False)
        output.seek(0)
        
        # Post to import
        response = self.app.post('/import', data={
            'file': (output, 'test.xlsx')
        }, content_type='multipart/form-data', follow_redirects=True)
        
        self.assertIn(b'Data imported successfully', response.data)
        
        # Verify DB
        house = House.query.filter_by(name='TEST_HOUSE_1').first()
        self.assertIsNotNone(house)
        
        flock = Flock.query.filter_by(house_id=house.id).first()
        self.assertIsNotNone(flock)
        self.assertEqual(flock.intake_date, date(2023, 1, 1))
        
        logs = DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date).all()
        self.assertEqual(len(logs), 2)
        
        # Check Day 1
        self.assertEqual(logs[0].date, date(2023, 1, 1))
        self.assertEqual(logs[0].culls_male, 1)
        self.assertEqual(logs[0].water_reading_1, 10000)
        
        # Check Day 2 & Water Calculation
        self.assertEqual(logs[1].date, date(2023, 1, 2))
        self.assertEqual(logs[1].water_reading_1, 10500)
        
        # Calculation: (105.00 - 100.00) * 1000 = 5000
        self.assertEqual(logs[1].water_intake_calculated, 5000.0)

if __name__ == '__main__':
    unittest.main()

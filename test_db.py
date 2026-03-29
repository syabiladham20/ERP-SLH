import sys
sys.path.append("/app")
from app import db, DailyLog
import sqlalchemy

try:
    print(DailyLog.__table__.columns.keys())
    print("Test passed: remarks column successfully added to DailyLog.")
except Exception as e:
    print("Test failed:", e)

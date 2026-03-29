from app import app, db, Standard, seed_standards_from_file
import time

def benchmark():
    with app.app_context():
        # Clean existing standards to measure creation as well
        Standard.query.delete()
        db.session.commit()

        start = time.perf_counter()
        success, msg = seed_standards_from_file()
        end = time.perf_counter()

        ms1 = (end - start) * 1000
        print(f"seed_standards_from_file took {ms1:.2f} ms")
        print(f"Result: {success}, {msg}")

if __name__ == '__main__':
    benchmark()

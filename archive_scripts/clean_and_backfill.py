import os
import sys
import shutil

# Set up the absolute paths
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
farm_db_path = os.path.join(instance_dir, 'farm.db')
farm_db_backup = os.path.join(instance_dir, 'farm_SAFE_BACKUP.db')
erp_db_path = os.path.join(instance_dir, 'erp.db')
slhop_db_path = os.path.join(basedir, 'slhop.db')

def perform_cleanup_and_backfill():
    print("--- Starting Production Sanitizer ---")

    # 1. Verify instance/farm.db exists
    if not os.path.exists(farm_db_path):
        print(f"[ERROR] CRITICAL: Active production database not found at {farm_db_path}")
        print("Aborting to prevent accidental data loss or empty initialization.")
        sys.exit(1)

    print(f"[OK] Found production database at {farm_db_path}")

    # 2. Backup farm.db
    try:
        shutil.copy2(farm_db_path, farm_db_backup)
        print(f"[OK] Created safe backup at {farm_db_backup}")
    except Exception as e:
        print(f"[ERROR] Failed to create backup: {e}")
        sys.exit(1)

    # 3. Clean ghost files
    for file_path in [erp_db_path, slhop_db_path]:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[OK] Deleted ghost file: {file_path}")
            except Exception as e:
                print(f"[WARNING] Failed to delete ghost file {file_path}: {e}")
        else:
            print(f"[INFO] Ghost file not found (already clean): {file_path}")

    # 4. Initialize App Context and Backfill
    print("\n--- Starting Database Backfill ---")
    try:
        from app import app, db, Flock, recalculate_flock_inventory
    except ImportError as e:
        print(f"[ERROR] Failed to import app components. Make sure you are in the project root. Error: {e}")
        sys.exit(1)

    with app.app_context():
        try:
            # Get all active flocks (or all flocks if you want to be safe)
            # You can filter by status if you only want active flocks: Flock.query.filter_by(status='Active').all()
            flocks = Flock.query.all()
            print(f"[INFO] Found {len(flocks)} flocks to process.")

            success_count = 0
            for flock in flocks:
                try:
                    recalculate_flock_inventory(flock.id)
                    success_count += 1
                    print(f"[OK] Recalculated inventory for Flock ID {flock.id} ({flock.name})")
                except Exception as e:
                    print(f"[ERROR] Failed to recalculate Flock ID {flock.id}: {e}")

            print(f"[SUCCESS] Backfill completed. Successfully processed {success_count} out of {len(flocks)} flocks.")

        except Exception as e:
            print(f"[ERROR] Database operations failed: {e}")

    print("\n--- Next Steps ---")
    print("1. Update your app.py using the code from app_config_fix.py")
    print("2. Run: touch /var/www/syabiladham_pythonanywhere_com_wsgi.py to reload the web server.")
    print("3. Check migrations: flask db stamp head")

if __name__ == '__main__':
    perform_cleanup_and_backfill()

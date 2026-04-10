from app import app, db, DailyLog, DailyLogPhoto
import os

with app.app_context():
    logs_with_photos = DailyLog.query.filter(DailyLog.photo_path != None, DailyLog.photo_path != '').all()
    count = 0
    for log in logs_with_photos:
        # Check if already migrated (optional, but safer)
        if DailyLogPhoto.query.filter_by(log_id=log.id).first():
            continue

        original_filename = os.path.basename(log.photo_path)

        # Try to recover original filename
        # Stored name format: {flock_id}_{date_str}_{file.filename}
        if log.flock and log.date:
            date_str = log.date.strftime('%y%m%d')
            prefix = f"{log.flock.flock_id}_{date_str}_"
            if original_filename.startswith(prefix):
                original_filename = original_filename[len(prefix):]

        photo = DailyLogPhoto(
            log_id=log.id,
            file_path=log.photo_path,
            original_filename=original_filename
        )
        db.session.add(photo)
        count += 1

    db.session.commit()
    print(f"Migrated {count} photos.")

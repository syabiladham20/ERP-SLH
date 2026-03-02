from app import app, db, SystemAuditLog
from datetime import datetime

with app.app_context():
    db.create_all()
    log = SystemAuditLog(
        timestamp=datetime.utcnow(),
        module="Biosecurity Sweep",
        action="Dead Code Audit & Bootstrap Icon Fix",
        performance_impact="Code footprint reduced, parsing overhead lowered. Faster UI execution.",
        notes="Files Modified: app.py, metrics.py, HTML templates.\nActions Taken: Replaced bi-tag with bi-eye. Removed unused variables (cum_cull, avg_stock vars) and dead block logic including WeeklyData table.\nIntegrity Check: Verified the UI loads and logic processes normally."
    )
    db.session.add(log)
    db.session.commit()
    print("Added Biosecurity Sweep audit log.")

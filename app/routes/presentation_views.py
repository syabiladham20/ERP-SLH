from flask import Blueprint, render_template, abort
from flask_login import login_required
from app.models.models import Flock
from app.utils import dept_required

presentation_views_bp = Blueprint('presentation_views', __name__, url_prefix='/presentation_studio')

@presentation_views_bp.route('/<int:flock_id>')
@login_required
@dept_required(['Admin', 'Farm', 'Management'])
def presentation_studio(flock_id):
    flock = Flock.query.get_or_404(flock_id)
    return render_template('presentation_studio.html', flock=flock)

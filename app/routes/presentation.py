from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.database import db
from app.models.models import ChartNote
from app.utils import dept_required
import logging

presentation_bp = Blueprint('presentation', __name__, url_prefix='/api/notes')

@presentation_bp.route('/<int:flock_id>/<string:chart_identifier>', methods=['GET'])
@login_required
def get_notes(flock_id, chart_identifier):
    try:
        notes = ChartNote.query.filter_by(flock_id=flock_id, chart_identifier=chart_identifier).all()
        return jsonify([
            {
                'id': note.id,
                'flock_id': note.flock_id,
                'chart_identifier': note.chart_identifier,
                'content': note.content,
                'pos_x': note.pos_x,
                'pos_y': note.pos_y,
                'width': note.width,
                'height': note.height,
                'created_at': note.created_at.isoformat() if note.created_at else None
            } for note in notes
        ])
    except Exception as e:
        logging.error(f"Error fetching chart notes: {e}")
        return jsonify({"error": "Failed to fetch notes"}), 500

@presentation_bp.route('/create', methods=['POST'])
@login_required
@dept_required('Admin')
def create_note():
    data = request.get_json()
    if not data or 'flock_id' not in data or 'chart_identifier' not in data or 'content' not in data:
        return jsonify({"error": "Missing required fields"}), 400
    try:
        new_note = ChartNote(
            flock_id=data['flock_id'],
            chart_identifier=data['chart_identifier'],
            content=data['content'],
            pos_x=data.get('pos_x', 0.0),
            pos_y=data.get('pos_y', 0.0),
            width=data.get('width', 100.0),
            height=data.get('height', 100.0)
        )
        db.session.add(new_note)
        db.session.commit()
        return jsonify({"message": "Note created successfully", "id": new_note.id}), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating chart note: {e}")
        return jsonify({"error": "Failed to create note"}), 500

@presentation_bp.route('/update/<int:note_id>', methods=['PUT'])
@login_required
@dept_required('Admin')
def update_note(note_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400
    try:
        note = ChartNote.query.get_or_404(note_id)
        if 'content' in data:
            note.content = data['content']
        if 'pos_x' in data:
            note.pos_x = data['pos_x']
        if 'pos_y' in data:
            note.pos_y = data['pos_y']
        if 'width' in data:
            note.width = data['width']
        if 'height' in data:
            note.height = data['height']

        db.session.commit()
        return jsonify({"message": "Note updated successfully"})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating chart note: {e}")
        return jsonify({"error": "Failed to update note"}), 500

@presentation_bp.route('/delete/<int:note_id>', methods=['DELETE'])
@login_required
@dept_required('Admin')
def delete_note(note_id):
    try:
        note = ChartNote.query.get_or_404(note_id)
        db.session.delete(note)
        db.session.commit()
        return jsonify({"message": "Note deleted successfully"})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting chart note: {e}")
        return jsonify({"error": "Failed to delete note"}), 500

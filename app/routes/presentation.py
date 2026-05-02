from flask import Blueprint, jsonify, request
from flask_login import login_required
from app.database import db
from app.models.models import StudioAnnotation
from app.utils import dept_required
import logging

presentation_bp = Blueprint('presentation', __name__, url_prefix='/api/presentation_studio')

@presentation_bp.route('/<int:flock_id>/<string:chart_identifier>', methods=['GET'])
@login_required
def get_annotations(flock_id, chart_identifier):
    try:
        annotations = StudioAnnotation.query.filter_by(
            flock_id=flock_id,
            chart_identifier=chart_identifier
        ).all()
        return jsonify([
            {
                'id': ann.id,
                'flock_id': ann.flock_id,
                'chart_identifier': ann.chart_identifier,
                'anchor_data_x': ann.anchor_data_x,
                'anchor_data_y': ann.anchor_data_y,
                'fabric_json': ann.fabric_json,
                'created_at': ann.created_at.isoformat() if ann.created_at else None
            } for ann in annotations
        ])
    except Exception as e:
        logging.error(f"Error fetching studio annotations: {e}")
        return jsonify({"error": "Failed to fetch annotations"}), 500

@presentation_bp.route('/create', methods=['POST'])
@login_required
@dept_required(['Admin', 'Farm', 'Management'])
def create_annotation():
    data = request.get_json()
    if not data or 'flock_id' not in data or 'chart_identifier' not in data or 'anchor_data_x' not in data or 'anchor_data_y' not in data or 'fabric_json' not in data:
        return jsonify({"error": "Missing required fields"}), 400
    try:
        new_annotation = StudioAnnotation(
            flock_id=data['flock_id'],
            chart_identifier=data['chart_identifier'],
            anchor_data_x=str(data['anchor_data_x']),
            anchor_data_y=float(data['anchor_data_y']),
            fabric_json=data['fabric_json']
        )
        db.session.add(new_annotation)
        db.session.commit()
        return jsonify({"message": "Annotation created successfully", "id": new_annotation.id}), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating studio annotation: {e}")
        return jsonify({"error": "Failed to create annotation"}), 500

@presentation_bp.route('/update/<int:annotation_id>', methods=['PUT'])
@login_required
@dept_required(['Admin', 'Farm', 'Management'])
def update_annotation(annotation_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400
    try:
        annotation = StudioAnnotation.query.get_or_404(annotation_id)
        if 'anchor_data_x' in data:
            annotation.anchor_data_x = str(data['anchor_data_x'])
        if 'anchor_data_y' in data:
            annotation.anchor_data_y = float(data['anchor_data_y'])
        if 'fabric_json' in data:
            annotation.fabric_json = data['fabric_json']

        db.session.commit()
        return jsonify({"message": "Annotation updated successfully"})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating studio annotation: {e}")
        return jsonify({"error": "Failed to update annotation"}), 500

@presentation_bp.route('/delete/<int:annotation_id>', methods=['DELETE'])
@login_required
@dept_required(['Admin', 'Farm', 'Management'])
def delete_annotation(annotation_id):
    try:
        annotation = StudioAnnotation.query.get_or_404(annotation_id)
        db.session.delete(annotation)
        db.session.commit()
        return jsonify({"message": "Annotation deleted successfully"})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting studio annotation: {e}")
        return jsonify({"error": "Failed to delete annotation"}), 500

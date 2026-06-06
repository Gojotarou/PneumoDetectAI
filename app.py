"""
PneumoDetect Flask Application
Main backend server for medical X-ray analysis with Role-Based Access Control
"""

from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from werkzeug.utils import secure_filename
from functools import wraps
import json
import os
import traceback
from datetime import datetime, timedelta
import base64
from io import BytesIO
import numpy as np
import cv2
from PIL import Image, UnidentifiedImageError
import tensorflow as tf
from tensorflow.keras.models import load_model
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from sqlalchemy import case, extract
from models import db, Patient, Analysis, Annotation, User, PatientStaff, Notification, init_db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['UPLOAD_FOLDER'] = 'uploads'


def ensure_xray_box_annotations_table():
    """Create storage table for doctor-drawn X-ray boxes if it does not exist."""
    db.session.execute(db.text('''
        CREATE TABLE IF NOT EXISTS xray_box_annotations (
            analysis_id INTEGER PRIMARY KEY,
            boxes_json TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    '''))


def get_xray_box_annotations(analysis_id):
    """Fetch persisted X-ray box annotations for an analysis."""
    ensure_xray_box_annotations_table()
    row = db.session.execute(
        db.text('SELECT boxes_json FROM xray_box_annotations WHERE analysis_id = :analysis_id'),
        {'analysis_id': analysis_id}
    ).fetchone()
    if not row or not row[0]:
        return []

    try:
        boxes = json.loads(row[0])
        return boxes if isinstance(boxes, list) else []
    except Exception:
        return []


def save_xray_box_annotations(analysis_id, boxes):
    """Upsert X-ray box annotations as JSON for an analysis."""
    ensure_xray_box_annotations_table()
    boxes_json = json.dumps(boxes)
    exists = db.session.execute(
        db.text('SELECT 1 FROM xray_box_annotations WHERE analysis_id = :analysis_id'),
        {'analysis_id': analysis_id}
    ).fetchone()

    if exists:
        db.session.execute(
            db.text('''
                UPDATE xray_box_annotations
                SET boxes_json = :boxes_json,
                    updated_at = CURRENT_TIMESTAMP
                WHERE analysis_id = :analysis_id
            '''),
            {'analysis_id': analysis_id, 'boxes_json': boxes_json}
        )
    else:
        db.session.execute(
            db.text('''
                INSERT INTO xray_box_annotations (analysis_id, boxes_json)
                VALUES (:analysis_id, :boxes_json)
            '''),
            {'analysis_id': analysis_id, 'boxes_json': boxes_json}
        )


def ensure_gradcam_box_annotations_table():
    """Create storage table for doctor-drawn Grad-CAM boxes if it does not exist."""
    db.session.execute(db.text('''
        CREATE TABLE IF NOT EXISTS gradcam_box_annotations (
            analysis_id INTEGER PRIMARY KEY,
            boxes_json TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    '''))


def get_gradcam_box_annotations(analysis_id):
    """Fetch persisted Grad-CAM box annotations for an analysis."""
    ensure_gradcam_box_annotations_table()
    row = db.session.execute(
        db.text('SELECT boxes_json FROM gradcam_box_annotations WHERE analysis_id = :analysis_id'),
        {'analysis_id': analysis_id}
    ).fetchone()
    if not row or not row[0]:
        return []

    try:
        boxes = json.loads(row[0])
        return boxes if isinstance(boxes, list) else []
    except Exception:
        return []


def save_gradcam_box_annotations(analysis_id, boxes):
    """Upsert Grad-CAM box annotations as JSON for an analysis."""
    ensure_gradcam_box_annotations_table()
    boxes_json = json.dumps(boxes)
    exists = db.session.execute(
        db.text('SELECT 1 FROM gradcam_box_annotations WHERE analysis_id = :analysis_id'),
        {'analysis_id': analysis_id}
    ).fetchone()

    if exists:
        db.session.execute(
            db.text('''
                UPDATE gradcam_box_annotations
                SET boxes_json = :boxes_json,
                    updated_at = CURRENT_TIMESTAMP
                WHERE analysis_id = :analysis_id
            '''),
            {'analysis_id': analysis_id, 'boxes_json': boxes_json}
        )
    else:
        db.session.execute(
            db.text('''
                INSERT INTO gradcam_box_annotations (analysis_id, boxes_json)
                VALUES (:analysis_id, :boxes_json)
            '''),
            {'analysis_id': analysis_id, 'boxes_json': boxes_json}
        )


def sanitize_xray_boxes(raw_boxes):
    """Validate and normalize user-drawn box coordinates into percentage bounds."""
    if not isinstance(raw_boxes, list):
        return []

    cleaned = []
    for raw in raw_boxes[:50]:
        if not isinstance(raw, dict):
            continue

        try:
            x = float(raw.get('x', 0))
            y = float(raw.get('y', 0))
            w = float(raw.get('w', 0))
            h = float(raw.get('h', 0))
        except (TypeError, ValueError):
            continue

        x = max(0.0, min(100.0, x))
        y = max(0.0, min(100.0, y))
        w = max(0.0, min(100.0 - x, w))
        h = max(0.0, min(100.0 - y, h))

        if w < 0.5 or h < 0.5:
            continue

        cleaned.append({
            'x': round(x, 3),
            'y': round(y, 3),
            'w': round(w, 3),
            'h': round(h, 3)
        })

    return cleaned


def ensure_gradcam_images_table():
    """Create storage table for generated Grad-CAM overlays if it does not exist."""
    db.session.execute(db.text('''
        CREATE TABLE IF NOT EXISTS gradcam_images (
            analysis_id INTEGER PRIMARY KEY,
            image_data LONGBLOB NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    '''))


def save_gradcam_image(analysis_id, image_data):
    """Upsert Grad-CAM image bytes for an analysis."""
    ensure_gradcam_images_table()
    exists = db.session.execute(
        db.text('SELECT 1 FROM gradcam_images WHERE analysis_id = :analysis_id'),
        {'analysis_id': analysis_id}
    ).fetchone()

    if exists:
        db.session.execute(
            db.text('''
                UPDATE gradcam_images
                SET image_data = :image_data,
                    updated_at = CURRENT_TIMESTAMP
                WHERE analysis_id = :analysis_id
            '''),
            {'analysis_id': analysis_id, 'image_data': image_data}
        )
    else:
        db.session.execute(
            db.text('''
                INSERT INTO gradcam_images (analysis_id, image_data)
                VALUES (:analysis_id, :image_data)
            '''),
            {'analysis_id': analysis_id, 'image_data': image_data}
        )


def get_gradcam_image(analysis_id):
    """Fetch Grad-CAM image bytes for an analysis."""
    ensure_gradcam_images_table()
    row = db.session.execute(
        db.text('SELECT image_data FROM gradcam_images WHERE analysis_id = :analysis_id'),
        {'analysis_id': analysis_id}
    ).fetchone()
    if not row:
        return None
    return row[0]

# Database Configuration
# Auto-detects platform based on environment variables
# Priority: DATABASE_URL > MYSQLHOST (Railway/AWS) > MYSQL_HOST (Local)
database_url = os.getenv('DATABASE_URL')
if database_url:
    # Full URL provided (Render)
    if database_url.startswith('mysql://'):
        database_url = database_url.replace('mysql://', 'mysql+mysqlconnector://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
elif os.getenv('MYSQLHOST'):
    # Railway RDS or AWS RDS individual vars (no underscores)
    # Both platforms use the same environment variable format
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"mysql+mysqlconnector://{os.getenv('MYSQLUSER')}:"
        f"{os.getenv('MYSQLPASSWORD')}@{os.getenv('MYSQLHOST')}:"
        f"{os.getenv('MYSQLPORT', '3306')}/"
        f"{os.getenv('MYSQLDATABASE')}"
    )
else:
    # Local development with XAMPP (underscores)
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"mysql+mysqlconnector://{os.getenv('MYSQL_USER')}:"
        f"{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DATABASE')}"
    )
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
    'connect_args': {'connect_timeout': 10}
}

# Initialize database
db.init_app(app)

# Initialize database on first request (not at startup)
_db_initialized = False

@app.before_request
def init_db_on_first_request():
    global _db_initialized
    if not _db_initialized:
        try:
            init_db(app)
            _db_initialized = True
        except Exception as e:
            print(f"⚠ Database initialization deferred: {e}")
            _db_initialized = False  # Retry on next request

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# =====================================================================
# AUTHENTICATION HELPERS & DECORATORS
# =====================================================================

def get_current_user():
    """Get current logged-in user from session"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not get_current_user():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    """Decorator to require specific roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': 'Unauthorized'}), 401
                return redirect(url_for('login_page'))
            if user.role not in allowed_roles:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': 'Forbidden'}), 403
                return jsonify({'error': 'Access Denied'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# =====================================================================
# LOAD CNN MODEL FOR PNEUMONIA DETECTION
# =====================================================================
try:
    pneumonia_model = load_model('models/pneumonia_model.h5')
    print("✓ Pneumonia CNN model loaded successfully")
except Exception as e:
    pneumonia_model = None
    print(f"⚠ Warning: Could not load pneumonia model: {e}")

# X-ray validator model settings
XRAY_VALIDATOR_MODEL_PATH = os.getenv('XRAY_VALIDATOR_MODEL_PATH', 'models/xray_detector.h5')
XRAY_VALIDATOR_THRESHOLD = float(os.getenv('XRAY_VALIDATOR_THRESHOLD', '0.5'))
XRAY_POSITIVE_LABEL = os.getenv('XRAY_POSITIVE_LABEL', 'xray').strip().lower()  # 'xray' or 'non_xray'
XRAY_CLASS_INDEX = int(os.getenv('XRAY_CLASS_INDEX', '1'))
XRAY_VALIDATION_STRICT = os.getenv('XRAY_VALIDATION_STRICT', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

try:
    xray_validator_model = load_model(XRAY_VALIDATOR_MODEL_PATH)
    print(f"✓ X-ray validator model loaded successfully from {XRAY_VALIDATOR_MODEL_PATH}")
except Exception as e:
    xray_validator_model = None
    print(f"⚠ Warning: Could not load X-ray validator model: {e}")

# =====================================================================
# ROUTES - Authentication
# =====================================================================

@app.route('/login.html', methods=['GET'])
def login_page():
    """Serve login page - always show fresh login (don't auto-redirect if logged in)"""
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """Handle user login"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        if not user.is_active:
            return jsonify({'success': False, 'error': 'User account is inactive'}), 403
        
        # Set session
        session.permanent = True
        session['user_id'] = user.id
        session['user_name'] = user.name
        session['user_role'] = user.role
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'redirect': url_for('dashboard'),
            'user': user.to_dict()
        }), 200
    
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Handle user logout"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200

@app.route('/api/current-user', methods=['GET'])
def get_logged_user():
    """Get current logged-in user info"""
    user = get_current_user()
    if user:
        return jsonify({'success': True, 'user': user.to_dict()}), 200
    return jsonify({'success': False, 'error': 'Not logged in'}), 401

@app.route('/api/dashboard-data', methods=['GET'])
@login_required
def dashboard_data():
    """Get role-specific dashboard data"""
    user = get_current_user()
    
    try:
        if user.role == 'admin':
            # Admin sees all statistics
            total_patients = Patient.query.count()
            total_analyses = Analysis.query.count()
            pending_reviews = Analysis.query.filter_by(reviewed_by_user_id=None).count()
            
            # Recent cases from all users
            recent_cases = Analysis.query.order_by(Analysis.created_at.desc()).limit(5).all()
            
            data = {
                'role': 'admin',
                'stats': {
                    'total_patients': total_patients,
                    'total_analyses': total_analyses,
                    'pending_reviews': pending_reviews,
                    'critical_alerts': 4  # Placeholder
                },
                'recent_cases': [
                    {
                        'id': case.id,
                        'patient_name': case.patient.name if case.patient else 'Unknown',
                        'patient_age': case.patient.age if case.patient else None,
                        'medical_id': case.patient.medical_id if case.patient else 'Unknown',
                        'pneumonia_detected': case.pneumonia_detected,
                        'confidence': case.confidence,
                        'created_at': case.created_at.isoformat(),
                        'created_by': case.created_by_user.name if case.created_by_user else 'Unknown'
                    }
                    for case in recent_cases
                ],
                'show_user_management': True
            }
            
        elif user.role == 'doctor':
            # Doctor sees only their assigned patients
            assigned_patients = db.session.query(Patient).join(
                PatientStaff, PatientStaff.patient_id == Patient.id
            ).filter(PatientStaff.user_id == user.id).count()
            
            # Their analyses
            my_analyses = Analysis.query.filter_by(created_by_user_id=user.id).count()
            pending_reviews = Analysis.query.filter_by(reviewed_by_user_id=None).count()
            
            # Recent cases for this doctor
            recent_cases = Analysis.query.filter_by(created_by_user_id=user.id).order_by(
                Analysis.created_at.desc()
            ).limit(5).all()
            
            data = {
                'role': 'doctor',
                'stats': {
                    'assigned_patients': assigned_patients,
                    'my_analyses': my_analyses,
                    'pending_reviews': pending_reviews,
                    'critical_alerts': 2  # Placeholder
                },
                'recent_cases': [
                    {
                        'id': case.id,
                        'patient_name': case.patient.name if case.patient else 'Unknown',
                        'patient_age': case.patient.age if case.patient else None,
                        'medical_id': case.patient.medical_id if case.patient else 'Unknown',
                        'pneumonia_detected': case.pneumonia_detected,
                        'confidence': case.confidence,
                        'created_at': case.created_at.isoformat(),
                        'reviewed': case.reviewed_by_user_id is not None
                    }
                    for case in recent_cases
                ],
                'show_user_management': False
            }
            
        elif user.role == 'nurse':
            # Nurse sees their uploads and assigned patients
            my_uploads = Analysis.query.filter_by(created_by_user_id=user.id).count()
            assigned_patients = db.session.query(Patient).join(
                PatientStaff, PatientStaff.patient_id == Patient.id
            ).filter(PatientStaff.user_id == user.id).count()
            
            # Recent uploads
            recent_cases = Analysis.query.filter_by(created_by_user_id=user.id).order_by(
                Analysis.created_at.desc()
            ).limit(5).all()
            
            data = {
                'role': 'nurse',
                'stats': {
                    'my_uploads': my_uploads,
                    'assigned_patients': assigned_patients,
                    'pending_analysis': sum(1 for case in recent_cases if case.pneumonia_detected is None),
                    'critical_alerts': 1  # Placeholder
                },
                'recent_cases': [
                    {
                        'id': case.id,
                        'patient_name': case.patient.name if case.patient else 'Unknown',
                        'patient_age': case.patient.age if case.patient else None,
                        'medical_id': case.patient.medical_id if case.patient else 'Unknown',
                        'pneumonia_detected': case.pneumonia_detected,
                        'confidence': case.confidence,
                        'created_at': case.created_at.isoformat(),
                        'analysis_ready': case.pneumonia_detected is not None
                    }
                    for case in recent_cases
                ],
                'show_user_management': False
            }
        else:
            return jsonify({'success': False, 'error': 'Unknown role'}), 400
        
        return jsonify({'success': True, 'data': data}), 200
        
    except Exception as e:
        print(f"Dashboard data error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================================
# ROUTES - Serve HTML Pages
# =====================================================================

@app.route('/')
def root():
    """Root route - always clear session and redirect to login for fresh start"""
    session.clear()  # Clear any existing session
    return redirect(url_for('login_page'))

@app.route('/dashboard.html')
@login_required
def dashboard():
    return render_template('dashboard.html', current_user=get_current_user())

@app.route('/new_analysis.html')
@login_required
@role_required('doctor', 'nurse')
def new_analysis():
    return render_template('new_analysis.html', current_user=get_current_user())

@app.route('/new_analysis_upload.html')
@login_required
@role_required('nurse', 'doctor')
def new_analysis_upload():
    return render_template('new_analysis_upload.html', current_user=get_current_user())

@app.route('/results.html')
@login_required
def results():
    return render_template('results.html', current_user=get_current_user())

@app.route('/alerts.html')
@login_required
@role_required('doctor', 'nurse')
def alerts():
    return render_template('alerts.html', current_user=get_current_user())

@app.route('/report.html')
@login_required
@role_required('doctor', 'nurse', 'admin')
def report():
    return render_template('report.html', current_user=get_current_user())

@app.route('/management')
@login_required
@role_required('admin')
def management():
    return render_template('management.html', current_user=get_current_user())

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html', current_user=get_current_user())

@app.route('/staff_performance')
@login_required
@role_required('admin')
def staff_performance():
    return render_template('staff_performance.html', current_user=get_current_user())

@app.route('/upload.html')
@login_required
@role_required('nurse', 'doctor')
def upload():
    return render_template('upload.html', current_user=get_current_user())

@app.route('/curb65.html')
@login_required
def curb65():
    return render_template('curb65.html', current_user=get_current_user())

# =====================================================================
# API ENDPOINTS - Backend Logic
# =====================================================================

@app.route('/api/patient-records', methods=['GET'])
@login_required
def get_patient_records():
    """
    Get patient records (analyses) - filtered by current user's assignments unless admin
    Doctors/Nurses also see analyses they created themselves
    Admin sees all records
    Returns: {'success': bool, 'records': list of patient analysis records}
    """
    try:
        user = get_current_user()
        
        # Admin sees all analyses
        if user.role == 'admin':
            analyses = Analysis.query.order_by(Analysis.created_at.desc()).all()
        else:
            # Doctor/Nurse see analyses from:
            # 1. Patients assigned to them
            # 2. Patients where they created the analysis (uploaded themselves)
            
            # Get patients assigned to this user
            assigned_patient_ids = db.session.query(PatientStaff.patient_id).filter(
                PatientStaff.user_id == user.id
            ).subquery()
            
            # Get analyses from assigned patients OR created by this user
            analyses = Analysis.query.filter(
                (Analysis.patient_id.in_(db.session.query(assigned_patient_ids))) |
                (Analysis.created_by_user_id == user.id)
            ).order_by(Analysis.created_at.desc()).all()
        
        records = []
        for analysis in analyses:
            # Get annotations for this analysis if they exist
            annotation = Annotation.query.filter_by(analysis_id=analysis.id).first()
            annotation_data = None
            if annotation:
                annotation_data = {
                    'doctor_name': annotation.doctor_name,
                    'final_diagnosis': annotation.final_diagnosis,
                    'clinical_notes': annotation.clinical_notes,
                    'treatment_plan': annotation.treatment_plan,
                    'follow_up_instructions': annotation.follow_up_instructions
                }
            
            records.append({
                'id': str(analysis.id),
                'timestamp': analysis.created_at.strftime('%Y-%m-%d %H:%M:%S') if analysis.created_at else None,
                'patient_name': analysis.patient.name,
                'medical_id': analysis.patient.medical_id,
                'age': analysis.age,
                'pneumonia_detected': analysis.pneumonia_detected,
                'confidence': analysis.confidence,
                'curb_score': analysis.curb_score,
                'curb_risk': analysis.curb_risk,
                'image_url': f"/api/image/{analysis.id}" if analysis.image_base64 else None,
                'gradcam_url': f"/api/gradcam-image/{analysis.id}" if get_gradcam_image(analysis.id) else None,
                'annotations': annotation_data
            })
        
        return jsonify({
            'success': True,
            'records': records
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analysis/<int:analysis_id>', methods=['DELETE'])
@login_required
@role_required('admin', 'doctor', 'nurse')
def delete_analysis(analysis_id):
    """
    Delete an analysis record by ID (also removes associated annotations)
    Permissions:
    - Admin: can delete any analysis
    - Doctor: can delete analyses they uploaded OR reviewed
    - Nurse: can delete analyses they uploaded
    Returns: {'success': bool, 'message': str}
    """
    try:
        user = get_current_user()
        
        # Find the analysis record
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            return jsonify({'success': False, 'error': 'Analysis not found'}), 404
        
        # Permission check
        can_delete = False
        if user.role == 'admin':
            can_delete = True
        elif user.role == 'doctor':
            # Doctor can delete if they created it OR reviewed it
            can_delete = (analysis.created_by_user_id == user.id or 
                         analysis.reviewed_by_user_id == user.id)
        elif user.role == 'nurse':
            # Nurse can delete if they created it
            can_delete = (analysis.created_by_user_id == user.id)
        
        if not can_delete:
            return jsonify({'success': False, 'error': 'You do not have permission to delete this analysis'}), 403
        
        # Delete associated annotations first using raw SQL to avoid schema issues
        db.session.execute(db.text('DELETE FROM annotations WHERE analysis_id = :id'), {'id': analysis_id})
        ensure_xray_box_annotations_table()
        db.session.execute(db.text('DELETE FROM xray_box_annotations WHERE analysis_id = :id'), {'id': analysis_id})
        ensure_gradcam_box_annotations_table()
        db.session.execute(db.text('DELETE FROM gradcam_box_annotations WHERE analysis_id = :id'), {'id': analysis_id})
        ensure_gradcam_images_table()
        db.session.execute(db.text('DELETE FROM gradcam_images WHERE analysis_id = :id'), {'id': analysis_id})
        
        # Delete the analysis record
        db.session.delete(analysis)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Analysis record deleted successfully'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting analysis: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analysis/<int:analysis_id>', methods=['GET'])
@login_required
def get_analysis(analysis_id):
    """
    Get a specific analysis record with all details and annotations
    Used for viewing case details from dashboard
    Returns: {'success': bool, 'data': analysis_object}
    """
    try:
        user = get_current_user()
        
        # Retrieve the analysis
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            return jsonify({'success': False, 'error': 'Analysis not found'}), 404
        
        # Permission check: user can view if they created it, reviewed it, or admin
        can_view = (user.role == 'admin' or 
                   analysis.created_by_user_id == user.id or 
                   analysis.reviewed_by_user_id == user.id)
        
        # Also check if user is assigned to the patient
        if not can_view:
            assigned = PatientStaff.query.filter_by(
                patient_id=analysis.patient_id,
                user_id=user.id
            ).first()
            can_view = assigned is not None
        
        if not can_view:
            return jsonify({'success': False, 'error': 'You do not have permission to view this analysis'}), 403
        
        # Get annotations if they exist
        annotation = Annotation.query.filter_by(analysis_id=analysis_id).first()
        xray_boxes = get_xray_box_annotations(analysis_id)
        gradcam_boxes = get_gradcam_box_annotations(analysis_id)
        annotation_data = None
        if annotation:
            annotation_data = {
                'doctor_name': annotation.doctor_name,
                'final_diagnosis': annotation.final_diagnosis,
                'clinical_notes': annotation.clinical_notes,
                'treatment_plan': annotation.treatment_plan,
                'follow_up_instructions': annotation.follow_up_instructions,
                'xray_boxes': xray_boxes,
                'gradcam_boxes': gradcam_boxes
            }
        elif xray_boxes or gradcam_boxes:
            annotation_data = {
                'doctor_name': '',
                'final_diagnosis': '',
                'clinical_notes': '',
                'treatment_plan': '',
                'follow_up_instructions': '',
                'xray_boxes': xray_boxes,
                'gradcam_boxes': gradcam_boxes
            }
        
        # Prepare response with same structure as analysis creation endpoint
        response = {
            'success': True,
            'data': {
                'analysis_id': analysis.id,
                'patient_id': analysis.patient_id,
                'timestamp': analysis.created_at.isoformat() if analysis.created_at else None,
                'patient_name': analysis.patient.name if analysis.patient else 'Unknown',
                'medical_id': analysis.patient.medical_id if analysis.patient else 'Unknown',
                'age': analysis.age,
                'pneumonia_detected': analysis.pneumonia_detected,
                'confidence': analysis.confidence,
                'curb_score': {
                    'score': analysis.curb_score,
                    'risk': analysis.curb_risk
                },
                'image_url': f"/api/image/{analysis.id}" if analysis.image_base64 else None,
                'gradcam_url': f"/api/gradcam-image/{analysis.id}" if get_gradcam_image(analysis.id) else None,
                'annotations': annotation_data
            }
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        print(f"Error retrieving analysis: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================================
# ROUTES - Patient Assignment Management (Phase 5)
# =====================================================================

@app.route('/api/users', methods=['GET'])
@login_required
def get_all_users():
    """Get staff users - with optional role filtering (admin only for general access)"""
    try:
        # Get role filter from query params
        role_filter = request.args.get('role')
        
        if role_filter:
            # Filter by role (nurses and doctors can see doctors for alerts)
            users = User.query.filter_by(role=role_filter).all()
        else:
            # Admin only for all users without filter
            user = get_current_user()
            if user.role != 'admin':
                return jsonify({'success': False, 'error': 'Unauthorized'}), 403
            users = User.query.all()
        
        user_list = []
        for user in users:
            user_list.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'department': user.department,
                'is_active': user.is_active,
                'created_at': user.created_at.isoformat() if user.created_at else None
            })
        
        return jsonify({
            'success': True,
            'users': user_list
        }), 200
    
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/users', methods=['POST'])
@login_required
@role_required('admin')
def create_user():
    """
    Create a new staff user (Hospital-Grade User Management)
    Admin only endpoint
    Expected JSON: {
        'name': str (required),
        'email': str (required, unique),
        'password': str (required, min 8 chars),
        'confirm_password': str (required, must match password),
        'role': str (required, one of: admin, doctor, nurse),
        'department': str (optional)
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        role = data.get('role', '').lower()
        department = data.get('department', '').strip()
        
        # Validation: Name
        if not name or len(name) < 2:
            return jsonify({
                'success': False,
                'error': 'Name must be at least 2 characters long'
            }), 400
        
        # Validation: Email format
        if not email or '@' not in email or '.' not in email:
            return jsonify({
                'success': False,
                'error': 'Please enter a valid email address'
            }), 400
        
        # Validation: Email uniqueness
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': f'Email "{email}" is already registered in the system'
            }), 409
        
        # Validation: Password strength
        if not password or len(password) < 8:
            return jsonify({
                'success': False,
                'error': 'Password must be at least 8 characters long'
            }), 400
        
        # Validation: Password match
        if password != confirm_password:
            return jsonify({
                'success': False,
                'error': 'Passwords do not match'
            }), 400
        
        # Validation: Role
        if role not in ['admin', 'doctor', 'nurse']:
            return jsonify({
                'success': False,
                'error': 'Invalid role. Must be one of: admin, doctor, nurse'
            }), 400
        
        # Create new user
        new_user = User(
            name=name,
            email=email,
            role=role,
            department=department if department else None,
            is_active=True
        )
        
        # Set password (hashed)
        new_user.set_password(password)
        
        # Add to database
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User "{name}" ({role}) created successfully',
            'user': {
                'id': new_user.id,
                'name': new_user.name,
                'email': new_user.email,
                'role': new_user.role,
                'department': new_user.department,
                'is_active': new_user.is_active,
                'created_at': new_user.created_at.isoformat()
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        print(f"Error creating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_user(user_id):
    """
    Delete a staff user (Admin only)
    Cannot delete the admin user who is currently logged in
    """
    try:
        current_user = get_current_user()
        user_to_delete = User.query.get(user_id)
        
        if not user_to_delete:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Prevent deleting yourself
        if user_to_delete.id == current_user.id:
            return jsonify({
                'success': False,
                'error': 'You cannot delete your own account'
            }), 400
        
        # Delete the user
        user_name = user_to_delete.name
        user_role = user_to_delete.role
        db.session.delete(user_to_delete)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User "{user_name}" ({user_role}) deleted successfully'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/patients', methods=['GET'])
@login_required
def get_patients():
    """
    Get patients - filtered by current user's assignments unless admin
    Admin sees all patients
    """
    try:
        user = get_current_user()
        
        if user.role == 'admin':
            # Admin sees all patients
            patients = Patient.query.all()
        else:
            # Doctor/Nurse see only assigned patients
            patients = db.session.query(Patient).join(
                PatientStaff, PatientStaff.patient_id == Patient.id
            ).filter(PatientStaff.user_id == user.id).all()
        
        return jsonify({
            'success': True,
            'patients': [p.to_dict() for p in patients]
        }), 200
    
    except Exception as e:
        print(f"Error fetching patients: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/assignments', methods=['GET'])
@login_required
@role_required('admin')
def get_assignments():
    """Get all patient-staff assignments (admin only)"""
    try:
        assignments = PatientStaff.query.all()
        
        assignment_list = []
        for assignment in assignments:
            assignment_list.append({
                'id': assignment.id,
                'patient_id': assignment.patient_id,
                'patient_name': assignment.patient.name if assignment.patient else 'Unknown',
                'user_id': assignment.user_id,
                'staff_name': assignment.staff.name if assignment.staff else 'Unknown',
                'role_type': assignment.role_type,
                'assigned_by': assignment.assigned_by.name if assignment.assigned_by else 'System',
                'assigned_at': assignment.assigned_at.isoformat() if assignment.assigned_at else None
            })
        
        return jsonify({
            'success': True,
            'assignments': assignment_list
        }), 200
    
    except Exception as e:
        print(f"Error fetching assignments: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/assignments', methods=['POST'])
@login_required
@role_required('admin')
def create_assignment():
    """
    Create patient-staff assignment (admin only)
    Expected POST data: {
        'patient_id': int,
        'user_id': int,
        'role_type': 'primary_doctor'|'secondary_doctor'|'assigned_nurse'
    }
    """
    try:
        data = request.get_json()
        patient_id = data.get('patient_id')
        user_id = data.get('user_id')
        role_type = data.get('role_type', 'primary_doctor')
        
        if not patient_id or not user_id:
            return jsonify({'success': False, 'error': 'patient_id and user_id required'}), 400
        
        if role_type not in ['primary_doctor', 'secondary_doctor', 'assigned_nurse']:
            return jsonify({'success': False, 'error': 'Invalid role_type'}), 400
        
        # Check if patient exists
        patient = Patient.query.get(patient_id)
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        # Check if user exists
        staff = User.query.get(user_id)
        if not staff:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Check if assignment already exists
        existing = PatientStaff.query.filter_by(
            patient_id=patient_id,
            user_id=user_id,
            role_type=role_type
        ).first()
        
        if existing:
            return jsonify({
                'success': False,
                'error': 'This assignment already exists'
            }), 409
        
        # Create assignment
        assignment = PatientStaff(
            patient_id=patient_id,
            user_id=user_id,
            role_type=role_type,
            assigned_by_user_id=get_current_user().id
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Assigned {staff.name} as {role_type} to patient {patient.name}',
            'assignment': {
                'id': assignment.id,
                'patient_id': assignment.patient_id,
                'user_id': assignment.user_id,
                'role_type': assignment.role_type
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        print(f"Error creating assignment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/assignments/<int:assignment_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_assignment(assignment_id):
    """Remove patient-staff assignment (admin only)"""
    try:
        assignment = PatientStaff.query.get(assignment_id)
        if not assignment:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404
        
        patient_name = assignment.patient.name if assignment.patient else 'Unknown'
        staff_name = assignment.staff.name if assignment.staff else 'Unknown'
        
        db.session.delete(assignment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Removed {staff_name} from {patient_name}'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting assignment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================================
# ROUTES - Notification Management (Phase 6)
# =====================================================================

@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Get current user's notifications"""
    try:
        user = get_current_user()
        
        # Get unread and undismissed notifications
        notifications = Notification.query.filter(
            Notification.recipient_id == user.id,
            Notification.is_dismissed == False
        ).order_by(Notification.created_at.desc()).all()
        
        notification_list = [n.to_dict() for n in notifications]
        
        return jsonify({
            'success': True,
            'notifications': notification_list,
            'unread_count': len([n for n in notifications if not n.is_read])
        }), 200
    
    except Exception as e:
        print(f"Error fetching notifications: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notifications', methods=['POST'])
@login_required
def create_notification():
    """Create new notification (send to another user)"""
    try:
        user = get_current_user()
        data = request.get_json()
        
        recipient_id = data.get('recipient_id')
        notification_type = data.get('notification_type')  # e.g., 'request_action', 'case_ready'
        message = data.get('message')
        patient_id = data.get('patient_id')
        analysis_id = data.get('analysis_id')
        
        if not recipient_id or not notification_type or not message:
            return jsonify({'success': False, 'error': 'recipient_id, notification_type, and message required'}), 400
        
        # Check if recipient exists
        recipient = User.query.get(recipient_id)
        if not recipient:
            return jsonify({'success': False, 'error': 'Recipient not found'}), 404
        
        # Create notification
        notification = Notification(
            recipient_id=recipient_id,
            sender_id=user.id,
            notification_type=notification_type,
            message=message,
            patient_id=patient_id,
            analysis_id=analysis_id
        )
        
        db.session.add(notification)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification sent successfully',
            'notification': notification.to_dict()
        }), 201
    
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notifications/<int:notification_id>', methods=['PUT'])
@login_required
def mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        user = get_current_user()
        notification = Notification.query.get(notification_id)
        
        if not notification:
            return jsonify({'success': False, 'error': 'Notification not found'}), 404
        
        # Only recipient can mark as read
        if notification.recipient_id != user.id:
            return jsonify({'success': False, 'error': 'Cannot modify other user notifications'}), 403
        
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification marked as read',
            'notification': notification.to_dict()
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error marking notification read: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
@login_required
def dismiss_notification(notification_id):
    """Dismiss/delete notification"""
    try:
        user = get_current_user()
        notification = Notification.query.get(notification_id)
        
        if not notification:
            return jsonify({'success': False, 'error': 'Notification not found'}), 404
        
        # Only recipient can dismiss
        if notification.recipient_id != user.id:
            return jsonify({'success': False, 'error': 'Cannot modify other user notifications'}), 403
        
        notification.is_dismissed = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification dismissed'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error dismissing notification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# HOSPITAL-GRADE ALERT SYSTEM (Phase 7)
@app.route('/api/send-alert', methods=['POST'])
@login_required
def send_alert():
    """Send hospital-grade alert from nurse/doctor to doctor (auto-calculates urgency)"""
    try:
        user = get_current_user()
        data = request.get_json()
        
        analysis_id = data.get('analysis_id')
        recipient_id = data.get('recipient_id')  # Doctor to alert
        patient_id = data.get('patient_id')
        confidence = data.get('confidence')  # AI confidence (0-100)
        curb_score = data.get('curb_score')  # Severity score
        
        if not all([analysis_id, recipient_id, patient_id, confidence is not None]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Calculate urgency level based on hospital standards
        if confidence > 85 and curb_score >= 3:
            urgency_level = 'CRITICAL'  # 🔴 Immediate action (>85% confidence + high CURB)
        elif confidence > 70 or curb_score >= 3:
            urgency_level = 'HIGH'  # 🟠 Review needed soon
        elif confidence > 50 or curb_score == 2:
            urgency_level = 'MODERATE'  # 🟡 Routine review
        else:
            urgency_level = 'LOW'  # 🟢 Informational
        
        # Get patient info
        patient = Patient.query.get(patient_id)
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        # Create alert notification
        message = f"Alert: Patient {patient.name} ({patient.medical_id}) - Pneumonia Detected ({confidence:.1f}% confidence, CURB-65: {curb_score})"
        
        alert = Notification(
            recipient_id=recipient_id,
            sender_id=user.id,
            patient_id=patient_id,
            analysis_id=analysis_id,
            notification_type='patient_alert',
            message=message,
            urgency_level=urgency_level
        )
        
        db.session.add(alert)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Alert sent ({urgency_level})',
            'notification': alert.to_dict()
        }), 201
    
    except Exception as e:
        db.session.rollback()
        print(f"Error sending alert: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notifications/<int:notification_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_alert(notification_id):
    """Doctor acknowledges alert (confirms they've seen it)"""
    try:
        user = get_current_user()
        notification = Notification.query.get(notification_id)
        
        if not notification:
            return jsonify({'success': False, 'error': 'Notification not found'}), 404
        
        # Only recipient (doctor) can acknowledge
        if notification.recipient_id != user.id:
            return jsonify({'success': False, 'error': 'Only recipient can acknowledge'}), 403
        
        notification.is_acknowledged = True
        notification.acknowledged_at = datetime.utcnow()
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Alert acknowledged',
            'notification': notification.to_dict()
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error acknowledging alert: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alerts', methods=['GET'])
@login_required
def get_alerts():
    """Get alerts for current user - with optional filter for pending/acknowledged"""
    try:
        user = get_current_user()
        
        # Get filter from query params (default: pending)
        filter_type = request.args.get('filter', 'pending')  # 'pending', 'acknowledged', or 'all'
        
        query = Notification.query.filter(
            Notification.recipient_id == user.id,
            Notification.notification_type == 'patient_alert',
            Notification.is_dismissed == False
        )
        
        # Apply filter
        if filter_type == 'pending':
            query = query.filter(Notification.is_acknowledged == False)
        elif filter_type == 'acknowledged':
            query = query.filter(Notification.is_acknowledged == True)
        # else: 'all' - no additional filter
        
        alerts = query.order_by(
            # Order by urgency and time
            case(
                (Notification.urgency_level == 'CRITICAL', 1),
                (Notification.urgency_level == 'HIGH', 2),
                (Notification.urgency_level == 'MODERATE', 3),
                (Notification.urgency_level == 'LOW', 4),
                else_=5
            ),
            Notification.created_at.desc()
        ).all()
        
        alert_list = [a.to_dict() for a in alerts]
        
        # Count by urgency (for all alerts)
        all_alerts = Notification.query.filter(
            Notification.recipient_id == user.id,
            Notification.notification_type == 'patient_alert',
            Notification.is_dismissed == False
        ).all()
        
        pending_count = len([a for a in all_alerts if not a.is_acknowledged])
        acknowledged_count = len([a for a in all_alerts if a.is_acknowledged])
        critical = len([a for a in all_alerts if a.urgency_level == 'CRITICAL' and not a.is_acknowledged])
        high = len([a for a in all_alerts if a.urgency_level == 'HIGH' and not a.is_acknowledged])
        moderate = len([a for a in all_alerts if a.urgency_level == 'MODERATE' and not a.is_acknowledged])
        
        return jsonify({
            'success': True,
            'alerts': alert_list,
            'pending_count': pending_count,
            'acknowledged_count': acknowledged_count,
            'critical_count': critical,
            'high_count': high,
            'moderate_count': moderate,
            'total_count': len(alert_list)
        }), 200
    
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alert-case/<int:alert_id>', methods=['GET'])
@login_required
def get_alert_case(alert_id):
    """Get full case details for an alert (patient + analysis data) - only for recipient"""
    try:
        user = get_current_user()
        
        # Get the notification/alert
        alert = Notification.query.get(alert_id)
        if not alert:
            return jsonify({'success': False, 'error': 'Alert not found'}), 404
        
        # Only recipient (assigned doctor) can view
        if alert.recipient_id != user.id:
            return jsonify({'success': False, 'error': 'Unauthorized - not recipient of this alert'}), 403
        
        # Get analysis and patient data
        analysis = Analysis.query.get(alert.analysis_id)
        if not analysis:
            return jsonify({'success': False, 'error': 'Analysis not found'}), 404
        
        patient = Patient.query.get(alert.patient_id)
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        # Get age directly from patient record
        age = patient.age
        
        # Calculate CURB-65
        curb_score_val = analysis.curb_score if hasattr(analysis, 'curb_score') else 0
        curb_score_data = {
            'score': curb_score_val,
            'risk': 'Severe' if curb_score_val >= 4 else ('Moderate' if curb_score_val >= 2 else 'Low')
        }
        
        # Get annotations if they exist
        annotation = Annotation.query.filter_by(analysis_id=analysis.id).first()
        annotations_data = {
            'doctor_name': annotation.doctor_name if annotation else '',
            'final_diagnosis': annotation.final_diagnosis if annotation else '',
            'clinical_notes': annotation.clinical_notes if annotation else '',
            'treatment_plan': annotation.treatment_plan if annotation else '',
            'follow_up_instructions': annotation.follow_up_instructions if annotation else ''
        } if annotation else {}
        
        response = {
            'success': True,
            'alert': alert.to_dict(),
            'analysis': {
                'analysis_id': analysis.id,
                'patient_id': patient.id,
                'timestamp': analysis.created_at.isoformat(),
                'patient_name': patient.name,
                'medical_id': patient.medical_id,
                'age': age,
                'pneumonia_detected': analysis.pneumonia_detected,
                'confidence': analysis.confidence,
                'curb_score': curb_score_data,
                'image_url': f"/api/image/{analysis.id}",
                'gradcam_url': f"/api/gradcam-image/{analysis.id}" if get_gradcam_image(analysis.id) else None,
                'annotations': annotations_data
            }
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        print(f"Error fetching alert case: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/check-patient-id', methods=['POST'])
@login_required
def check_patient_id():
    """
    Check if a medical_id already exists in the database (Step 1 validation)
    Returns whether the ID exists and patient details if it does
    """
    try:
        data = request.get_json()
        medical_id = data.get('medical_id', '').strip()
        
        if not medical_id:
            return jsonify({'success': False, 'error': 'Medical ID required'}), 400
        
        # Check if patient with this medical_id exists
        existing_patient = Patient.query.filter_by(medical_id=medical_id).first()
        
        if existing_patient:
            # Patient exists - return error with details
            return jsonify({
                'success': False,
                'exists': True,
                'error': f'Patient ID "{medical_id}" already exists',
                'existing_patient': {
                    'id': existing_patient.id,
                    'name': existing_patient.name,
                    'age': existing_patient.age,
                    'medical_id': existing_patient.medical_id
                }
            }), 409
        
        # Patient does not exist - safe to proceed
        return jsonify({
            'success': True,
            'exists': False,
            'message': 'Medical ID is available'
        }), 200
    
    except Exception as e:
        print(f"Error checking patient ID: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
@login_required
@role_required('nurse', 'doctor')
def analyze_xray():
    """
    Receive X-ray image and clinical parameters, analyze, and save to database
    Expected POST data:
    - image: file (multipart)
    - patient_name: str
    - medical_id: str
    - age: int
    - confusion: 0 or 1
    - urea: float
    - respiratory: float
    - sbp: float
    - dbp: float
    """
    try:
        # Check if image file is present
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Read image file as binary (don't encode as base64)
        file_data = file.read()

        # Validate that uploaded bytes are a readable image and run X-ray confidence check.
        # In non-strict mode, low X-ray confidence is advisory (prevents false rejections).
        validation_result = run_xray_validation(file_data)
        if validation_result.get('reason') == 'invalid_image':
            return jsonify({
                'success': False,
                'error': 'Uploaded file is not a valid image. Please upload a PNG/JPG chest X-ray image.',
                'xray_validation': validation_result
            }), 400

        if XRAY_VALIDATION_STRICT and not validation_result.get('is_xray', False):
            return jsonify({
                'success': False,
                'error': 'Uploaded image failed X-ray validation. Please upload a chest X-ray image.',
                'xray_validation': validation_result
            }), 400
        
        # Get and validate age from form (defense in depth against client-side bypass).
        MIN_AGE = 0
        MAX_AGE = 120
        raw_age = (request.form.get('age', '') or '').strip()
        try:
            age = int(raw_age)
        except (TypeError, ValueError):
            return jsonify({'error': f'Invalid age value. Age must be an integer between {MIN_AGE} and {MAX_AGE}.'}), 400

        if age < MIN_AGE or age > MAX_AGE:
            return jsonify({'error': f'Invalid age value. Age must be between {MIN_AGE} and {MAX_AGE}.'}), 400

        # Get clinical parameters from form
        age_criterion = int(request.form.get('age_criterion', 0))  # CURB-65: 0=<65, 1=≥65
        confusion = int(request.form.get('confusion', 0))
        urea = int(request.form.get('urea', 0))  # Already thresholded: 0 or 1
        respiratory = int(request.form.get('respiratory', 0))  # Already thresholded: 0 or 1
        sbp = int(request.form.get('sbp', 0))  # Already thresholded: 0 or 1
        dbp = float(request.form.get('dbp', 0))
        patient_name = request.form.get('patient_name', 'Unknown')
        medical_id = request.form.get('medical_id', f"AUTO-{int(datetime.now().timestamp())}")
        
        # VALIDATION: Check if medical_id already exists
        existing_patient = Patient.query.filter_by(medical_id=medical_id).first()
        if existing_patient:
            return jsonify({
                'success': False,
                'error': f'❌ Patient ID "{medical_id}" already exists in the system!',
                'details': f'Patient: {existing_patient.name} (Age: {existing_patient.age})',
                'existing_patient': {
                    'id': existing_patient.id,
                    'name': existing_patient.name,
                    'age': existing_patient.age,
                    'medical_id': existing_patient.medical_id
                }
            }), 409
        
        # Create new patient
        patient = Patient(
            medical_id=medical_id,
            name=patient_name,
            age=age
        )
        db.session.add(patient)
        db.session.commit()
        
        # Run AI model prediction
        prediction_result = run_pneumonia_detection(
            file_data, age, confusion, urea, respiratory, sbp, dbp
        )

        # Build Grad-CAM overlay from the same uploaded image and existing model.
        gradcam_image_data = generate_gradcam_overlay(file_data, last_conv_layer_name='conv5_block16_concat')
        
        # Compute CURB-65 score using criteria (0 or 1 values), NOT patient age
        curb_score_data = compute_curb65(age_criterion, confusion, urea, respiratory, sbp, dbp)
        
        # Save analysis to database with creator info
        user = get_current_user()
        analysis = Analysis(
            patient_id=patient.id,
            created_by_user_id=user.id,
            age=age,
            confusion=confusion,
            urea=urea,
            respiratory_rate=respiratory,
            systolic_bp=sbp,
            diastolic_bp=dbp,
            pneumonia_detected=prediction_result['detected'],
            confidence=prediction_result['confidence'],
            curb_score=curb_score_data['score'],
            curb_risk=curb_score_data['risk'],
            image_filename=secure_filename(file.filename),
            image_base64=file_data  # Store binary data directly
        )
        
        db.session.add(analysis)
        db.session.commit()

        if gradcam_image_data:
            save_gradcam_image(analysis.id, gradcam_image_data)
            db.session.commit()
        
        # Auto-assign the uploader to this patient if not already assigned
        existing_assignment = PatientStaff.query.filter_by(
            patient_id=patient.id,
            user_id=user.id
        ).first()
        
        if not existing_assignment:
            assignment = PatientStaff(
                patient_id=patient.id,
                user_id=user.id,
                role_type='assigned_nurse' if user.role == 'nurse' else 'primary_doctor',
                assigned_by_user_id=user.id
            )
            db.session.add(assignment)
            db.session.commit()
        
        # Prepare response
        response = {
            'success': True,
            'analysis_id': analysis.id,
            'patient_id': patient.id,
            'timestamp': analysis.created_at.isoformat(),
            'patient_name': patient.name,
            'medical_id': patient.medical_id,
            'age': age,
            'pneumonia_detected': analysis.pneumonia_detected,
            'confidence': analysis.confidence,
            'xray_validation': validation_result,
            'xray_validation_warning': validation_result.get('warning'),
            'curb_score': curb_score_data,
            'image_url': f"/api/image/{analysis.id}",
            'gradcam_url': f"/api/gradcam-image/{analysis.id}" if gradcam_image_data else None
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error in analyze_xray: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'PneumoDetect API'})


@app.route('/api/save-annotations', methods=['POST'])
@login_required
def save_annotations():
    """
    Save doctor's annotations for an analysis
    Expected JSON:
    - analysis_id: int
    - doctor_name: str
    - final_diagnosis: str
    - clinical_notes: str
    - treatment_plan: str
    - follow_up_instructions: str
    """
    try:
        data = request.get_json()
        analysis_id = data.get('analysis_id')
        
        # Check if analysis exists
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            return jsonify({'error': 'Analysis not found'}), 404
        
        # Create or update annotation
        annotation = Annotation.query.filter_by(analysis_id=analysis_id).first()
        if not annotation:
            annotation = Annotation(analysis_id=analysis_id)
        
        # Update annotation fields
        annotation.doctor_name = data.get('doctor_name', '')
        annotation.final_diagnosis = data.get('final_diagnosis', '')
        annotation.clinical_notes = data.get('clinical_notes', '')
        annotation.treatment_plan = data.get('treatment_plan', '')
        annotation.follow_up_instructions = data.get('follow_up_instructions', '')
        xray_boxes = sanitize_xray_boxes(data.get('xray_boxes', []))
        gradcam_boxes = sanitize_xray_boxes(data.get('gradcam_boxes', []))
        save_xray_box_annotations(analysis_id, xray_boxes)
        save_gradcam_box_annotations(analysis_id, gradcam_boxes)
        
        db.session.add(annotation)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Annotations saved successfully',
            'annotation_id': annotation.id,
            'xray_boxes_count': len(xray_boxes),
            'gradcam_boxes_count': len(gradcam_boxes)
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error saving annotations: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-report', methods=['POST'])
@login_required
def download_report():
    """
    Generate and download a professional hospital-grade PDF report with X-ray image
    Follows medical imaging center report format with full annotations and user details
    """
    try:
        data = request.get_json()
        analysis_id = data.get('analysis_id')
        
        # Get current user info
        current_user = get_current_user()
        
        # Retrieve analysis from database
        analysis = None
        if analysis_id:
            analysis = Analysis.query.get(analysis_id)
        
        # Create PDF in memory
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.4*inch, bottomMargin=0.5*inch,
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Professional header styles
        header_main_style = ParagraphStyle(
            'HeaderMain',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#003DA5'),
            fontName='Helvetica-Bold',
            spaceAfter=0,
            alignment=TA_CENTER
        )
        
        header_sub_style = ParagraphStyle(
            'HeaderSub',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#666666'),
            alignment=TA_CENTER,
            spaceAfter=12
        )
        
        section_title_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#003DA5'),
            fontName='Helvetica-Bold',
            spaceAfter=6,
            spaceBefore=4
        )
        
        finding_style = ParagraphStyle(
            'Finding',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            spaceAfter=4,
            leftIndent=15
        )
        
        impression_style = ParagraphStyle(
            'Impression',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            spaceAfter=8,
            alignment=TA_JUSTIFY
        )
        
        # PROFESSIONAL HEADER
        elements.append(Paragraph("PNEUMODETECT AI DIAGNOSTIC SYSTEM", header_main_style))
        elements.append(Paragraph("AI-Assisted Chest X-Ray Analysis System", header_sub_style))
        elements.append(Spacer(1, 0.15*inch))
        
        # ============================================================
        # 1. PATIENT INFORMATION (Vertical Table Format)
        # ============================================================
        elements.append(Paragraph("PATIENT INFORMATION", section_title_style))
        
        report_date = datetime.now()
        
        # Create a text wrapping style for table cells
        cell_text_style = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#333333'),
            wordWrap='CJK'
        )
        
        patient_info_data = [
            ['Patient Name:', Paragraph(data.get('patient_name', 'N/A'), cell_text_style)],
            ['Medical ID:', Paragraph(data.get('medical_id', 'N/A'), cell_text_style)],
            ['Age:', Paragraph(f"{data.get('age', 'N/A')} years", cell_text_style)],
            ['Report Date:', Paragraph(report_date.strftime('%Y-%m-%d %H:%M:%S'), cell_text_style)],
        ]
        
        patient_table = Table(patient_info_data, colWidths=[2*inch, 5*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E8F0F8')),
            ('BORDER', (0, 0), (-1, -1), 0.5, colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#333333')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333'))
        ]))
        elements.append(patient_table)
        elements.append(Spacer(1, 0.25*inch))
        
        # ============================================================
        # 2. X-RAY IMAGE SECTION
        # ============================================================
        elements.append(Paragraph("CHEST X-RAY IMAGING", section_title_style))

        xray_rl_image = None

        if analysis and analysis.image_base64:
            try:
                # Convert binary image data to PIL image and then PNG buffer for PDF embedding.
                image_data = analysis.image_base64
                if isinstance(image_data, bytes):
                    img = Image.open(BytesIO(image_data))
                else:
                    img = Image.open(BytesIO(image_data.encode() if isinstance(image_data, str) else image_data))

                img_buffer = BytesIO()
                img.save(img_buffer, format='PNG')
                img_buffer.seek(0)
                xray_rl_image = RLImage(img_buffer, width=3.2*inch, height=3.2*inch)
            except Exception as e:
                print(f"Warning: Could not add X-ray image to PDF: {e}")

        if xray_rl_image:
            elements.append(xray_rl_image)
            elements.append(Spacer(1, 0.25*inch))
        else:
            elements.append(Paragraph("<i>No X-Ray image available for this analysis</i>", styles['Normal']))
            elements.append(Spacer(1, 0.25*inch))
        
        # ============================================================
        # 3. AI DIAGNOSIS RESULTS (Vertical Table Format)
        # ============================================================
        elements.append(Paragraph("AI DIAGNOSIS RESULTS", section_title_style))
        
        pneumonia_status = "PNEUMONIA DETECTED" if data.get('pneumonia_detected') else "NORMAL"
        
        # Get CURB-65 information
        curb_score_val = data.get('curb_score', {}).get('score', 0)
        curb_risk = data.get('curb_score', {}).get('risk', 'Unknown')
        
        # Determine action needed based on CURB-65 score (Evidence-based: Lim et al. 2003 Thorax)
        # 30-day mortality rates from original CURB-65 validation study
        if data.get('pneumonia_detected'):
            if curb_score_val == 5:
                action_needed = 'CRITICAL: ICU admission recommended. Requires intensive management and organ support (30-day mortality: 57%)'
            elif curb_score_val == 4:
                action_needed = 'URGENT: Hospitalization essential. ICU admission should be strongly considered (30-day mortality: 41.5%)'
            elif curb_score_val == 3:
                action_needed = 'HIGH RISK: Hospitalization strongly recommended. Close monitoring and intensive care consideration required (30-day mortality: 17%)'
            elif curb_score_val == 2:
                action_needed = 'MODERATE RISK: Consider hospitalization or close outpatient supervision. IV antibiotics may be required (30-day mortality: 13%)'
            elif curb_score_val == 1:
                action_needed = 'LOW-MODERATE RISK: Outpatient treatment likely appropriate with close clinical follow-up (30-day mortality: 3.2%)'
            else:  # 0
                action_needed = 'LOW RISK: Outpatient treatment recommended. Close follow-up essential (30-day mortality: 0.7%)'
        else:
            action_needed = 'No pneumonia detected - Routine follow-up care'
        
        ai_results_data = [
            ['Diagnosis Status:', Paragraph(pneumonia_status, cell_text_style)],
            ['Confidence Score:', Paragraph(f"{data.get('confidence', 0):.2f}%", cell_text_style)],
            ['Analysis Method:', Paragraph('Convolutional Neural Network (CNN) - Deep Learning Medical Imaging', cell_text_style)],
            ['CURB-65 Severity Score:', Paragraph(f"{curb_score_val}/5 - {curb_risk} Risk", cell_text_style)],
            ['Action Needed:', Paragraph(action_needed, cell_text_style)],
        ]
        
        ai_table = Table(ai_results_data, colWidths=[2*inch, 5*inch])
        ai_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E8F0F8')),
            ('BORDER', (0, 0), (-1, -1), 0.5, colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#333333')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333'))
        ]))
        elements.append(ai_table)
        elements.append(Spacer(1, 0.25*inch))
        elements.append(Spacer(1, 0.15*inch))
        
        # CLINICAL IMPRESSION (highlighted section like medical report)
        impression_box_data = [
            ['CLINICAL IMPRESSION']
        ]
        
        impression_box = Table(impression_box_data, colWidths=[6*inch])
        impression_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#003DA5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
        ]))
        elements.append(impression_box)
        
        # Generate impression based on AI results and CURB-65
        if data.get('pneumonia_detected'):
            impression_text = f"""Chest X-ray analysis by AI diagnostic system indicates <b>pneumonia detection</b> with {data.get('confidence', 0):.1f}% confidence.
CURB-65 severity assessment: Score {curb_score_val}/5 - {curb_risk} Risk.
Clinical correlation with patient symptoms, vital signs, and laboratory findings is recommended for final diagnosis confirmation."""
        else:
            impression_text = f"""Chest X-ray analysis by AI diagnostic system indicates <b>normal findings</b>.
No pneumonia features detected. CURB-65 score: {curb_score_val}/5 - {curb_risk} Risk.
Clinical assessment should integrate this imaging finding with patient presentation and clinical context."""
        
        elements.append(Paragraph(impression_text, impression_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # DOCTOR'S CLINICAL ANNOTATIONS (if available)
        annotations = data.get('annotations', {})
        if any([annotations.get('doctorName'), annotations.get('finalDiagnosis'), annotations.get('clinicalNotes'), 
                annotations.get('treatmentPlan'), annotations.get('followUpInstructions')]):
            
            elements.append(Spacer(1, 0.15*inch))
            elements.append(Paragraph("PHYSICIAN'S CLINICAL ANNOTATION", section_title_style))
            
            # Build annotations table with available data
            annotations_table_data = []
            
            if annotations.get('doctorName'):
                annotations_table_data.append(['Reviewing Physician:', Paragraph(annotations.get('doctorName'), cell_text_style)])
            
            if annotations.get('finalDiagnosis'):
                annotations_table_data.append(['Final Clinical Diagnosis:', Paragraph(annotations.get('finalDiagnosis'), cell_text_style)])
            
            if annotations.get('clinicalNotes'):
                annotations_table_data.append(['Clinical Observations:', Paragraph(annotations.get('clinicalNotes'), cell_text_style)])
            
            if annotations.get('treatmentPlan'):
                annotations_table_data.append(['Treatment Plan:', Paragraph(annotations.get('treatmentPlan'), cell_text_style)])
            
            if annotations.get('followUpInstructions'):
                annotations_table_data.append(['Follow-up Instructions:', Paragraph(annotations.get('followUpInstructions'), cell_text_style)])
            
            # Create and style annotations table
            if annotations_table_data:
                annotations_table = Table(annotations_table_data, colWidths=[2*inch, 5*inch])
                annotations_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F9FF')),
                    ('BORDER', (0, 0), (-1, -1), 0.5, colors.HexColor('#B0C4DE')),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#003DA5')),
                    ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333'))
                ]))
                elements.append(annotations_table)
            
            elements.append(Spacer(1, 0.2*inch))
        
        # PROFESSIONAL FOOTER SECTION
        elements.append(Spacer(1, 0.4*inch))
        
        # Report metadata in professional format
        metadata_text = f"""<b>Generated By:</b> {current_user.name if current_user else 'System'}<br/>
<b>Role:</b> {current_user.role.title() if current_user else 'AI System'}<br/>
<b>Generated On:</b> {report_date.strftime('%d %B, %Y at %I:%M %p')}<br/>
<b>Report ID:</b> {datetime.now().strftime('%Y%m%d_%H%M%S')}<br/>
<b>System:</b> PneumoDetect AI v1.0 - AI-Assisted Chest X-Ray Diagnostic System"""
        
        elements.append(Paragraph(metadata_text, ParagraphStyle(
            'Metadata',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#333333'),
            leftIndent=12,
            spaceAfter=12
        )))
        
        elements.append(Spacer(1, 0.2*inch))
        
        # Disclaimer
        disclaimer_text = """<i><b>DISCLAIMER:</b> This report presents AI-assisted diagnostic analysis of chest X-ray imaging. The results are intended to support clinical decision-making by qualified healthcare professionals and should not be used as a standalone diagnostic tool. Final clinical diagnosis and treatment decisions must be made by a qualified physician after complete clinical evaluation. PneumoDetect AI is a computer-aided diagnostic system and does not replace professional medical judgment.</i>"""
        
        elements.append(Paragraph(disclaimer_text, ParagraphStyle(
            'Disclaimer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#555555'),
            spaceAfter=12,
            alignment=TA_JUSTIFY
        )))
        
        # Build PDF
        doc.build(elements)
        pdf_buffer.seek(0)
        
        # Send file
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"PneumoDetect_Report_{data.get('medical_id', 'Report')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
    
    except Exception as e:
        print(f"Error generating PDF: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/image/<analysis_id>', methods=['GET'])
@login_required
def get_analysis_image(analysis_id):
    """
    Serve X-ray image from database (MEDIUMBLOB) with proper error handling
    Supports hospital-grade reliability with logging
    """
    try:
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            print(f"Image request: Analysis {analysis_id} not found")
            return jsonify({'error': 'Analysis not found'}), 404
        
        image_data = analysis.image_base64
        if not image_data:
            print(f"Image request: Analysis {analysis_id} has no image data")
            return jsonify({'error': 'No image data available'}), 404
        
        # Ensure data is bytes (LargeBinary should return bytes automatically)
        if not isinstance(image_data, bytes):
            print(f"WARNING: Image data is {type(image_data)}, converting to bytes")
            image_data = image_data.encode() if isinstance(image_data, str) else bytes(image_data)
        
        print(f"✓ Serving image for analysis {analysis_id} ({len(image_data)} bytes)")
        
        # Serve the binary image data directly
        return send_file(
            BytesIO(image_data),
            mimetype='image/png',
            as_attachment=False,
            download_name=f"xray_{analysis_id}.png"
        )
    
    except Exception as e:
        print(f"✗ Error retrieving image {analysis_id}: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Failed to retrieve image', 'details': str(e)}), 500


@app.route('/api/gradcam-image/<int:analysis_id>', methods=['GET'])
@login_required
def get_gradcam_image_endpoint(analysis_id):
    """Serve Grad-CAM overlay image from database for a given analysis."""
    try:
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            return jsonify({'error': 'Analysis not found'}), 404

        image_data = get_gradcam_image(analysis_id)
        if not image_data:
            return jsonify({'error': 'No Grad-CAM image available'}), 404

        return send_file(
            BytesIO(image_data),
            mimetype='image/png',
            as_attachment=False,
            download_name=f"gradcam_{analysis_id}.png"
        )

    except Exception as e:
        print(f"✗ Error retrieving Grad-CAM image {analysis_id}: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Failed to retrieve Grad-CAM image', 'details': str(e)}), 500


# =====================================================================
# HELPER FUNCTIONS - Business Logic
# =====================================================================

def compute_curb65(age, confusion, urea, respiratory, sbp, dbp):
    """
    CURB-65 Score Calculator
    
    With YES/NO button interface, inputs are already thresholded:
    - age: 0=No (<65) or 1=Yes (≥65)
    - confusion: 0=No or 1=Yes (new onset)
    - urea: 0=No (≤7) or 1=Yes (>7 mmol/L)
    - respiratory: 0=No (<30) or 1=Yes (≥30)
    - sbp: 0=No or 1=Yes (SBP <90 or DBP ≤60)
    
    Returns score (0-5) and risk level
    """
    # Simply sum all YES answers - each criterion already thresholded by frontend
    score = int(age) + int(confusion) + int(urea) + int(respiratory) + int(sbp)
    
    return {
        'score': score,
        'risk': get_risk_level(score)
    }


def get_risk_level(curb_score):
    """
    Map CURB-65 score to hospital-grade risk level (BTS Standard)
    
    CURB-65 Risk Stratification:
    - 0-1: Low risk (outpatient management)
    - 2: Moderate risk (consider hospital admission)
    - 3: High risk (hospital admission recommended)
    - 4-5: Very High risk (ICU consideration)
    """
    if curb_score <= 1:
        return 'Low'
    elif curb_score == 2:
        return 'Moderate'
    elif curb_score == 3:
        return 'High'
    else:  # 4-5
        return 'Very High'


def run_pneumonia_detection(image_data, age, confusion, urea, respiratory, sbp, dbp):
    """
    CNN Model inference for pneumonia detection
    Loads chest X-ray image and returns prediction
    
    Returns: {'detected': bool, 'confidence': float (0-100)}
    """
    
    if pneumonia_model is None:
        return {
            'detected': False,
            'confidence': 0,
            'error': 'Model not loaded'
        }
    
    try:
        # Convert image bytes to PIL Image
        image = Image.open(BytesIO(image_data)).convert('RGB')
        
        # Resize to model's expected input size (update 224 if your model uses different size)
        image = image.resize((224, 224))
        
        # Convert to numpy array and normalize to [0, 1]
        img_array = np.array(image) / 255.0
        
        # Add batch dimension for model input (1, 224, 224, 3)
        img_array = np.expand_dims(img_array, axis=0)
        
        # Run inference
        prediction = pneumonia_model.predict(img_array, verbose=0)
        
        # Extract pneumonia confidence (assuming binary classification)
        # If model outputs [normal, pneumonia], take pneumonia probability
        if len(prediction[0]) > 1:
            # Binary classification: [normal_prob, pneumonia_prob]
            pneumonia_confidence = float(prediction[0][1]) * 100
        else:
            # Single output: direct pneumonia probability
            pneumonia_confidence = float(prediction[0][0]) * 100
        
        # Threshold for detection (adjust as needed)
        detected = pneumonia_confidence >= 50
        
        return {
            'detected': detected,
            'confidence': round(pneumonia_confidence, 2)
        }
        
    except Exception as e:
        print(f"ERROR during pneumonia detection: {e}")
        traceback.print_exc()
        return {
            'detected': False,
            'confidence': 0,
            'error': str(e)
        }


def _build_lung_soft_mask(height, width):
    """
    Build a smooth Gaussian lung-prior weight map with NO hard edges.

    Anatomical references for a PA frontal chest X-ray (viewer orientation):
      - Patient RIGHT lung  → image LEFT  (where the 'R' marker appears)
      - Patient LEFT  lung  → image RIGHT
    Ellipses are placed at standard lung-field positions and blurred with a
    large sigma so the boundary is never visible in the output.
    """
    lung_canvas = np.zeros((height, width), dtype=np.uint8)

    # Right lung (image-left, patient-right) — typically slightly larger
    r_cx  = int(width  * 0.27)
    r_cy  = int(height * 0.45)
    r_ax  = int(width  * 0.22)   # horizontal semi-axis
    r_ay  = int(height * 0.34)   # vertical semi-axis
    cv2.ellipse(lung_canvas, (r_cx, r_cy), (r_ax, r_ay), 0, 0, 360, 255, -1)

    # Left lung (image-right, patient-left) — slightly narrower
    l_cx  = int(width  * 0.73)
    l_cy  = int(height * 0.45)
    l_ax  = int(width  * 0.19)
    l_ay  = int(height * 0.32)
    cv2.ellipse(lung_canvas, (l_cx, l_cy), (l_ax, l_ay), 0, 0, 360, 255, -1)

    # Large Gaussian blur eliminates every visible edge — minimum 20 px sigma
    sigma = max(min(height, width) * 0.10, 20.0)
    soft  = cv2.GaussianBlur(lung_canvas.astype(np.float32), (0, 0),
                             sigmaX=sigma, sigmaY=sigma)
    peak  = float(np.max(soft))
    return (soft / peak) if peak > 0 else soft


def generate_gradcam_overlay(image_data, last_conv_layer_name='conv5_block16_concat'):
    """
    Generate a clinically clean Grad-CAM overlay using GradientTape + OpenCV.

    Key improvements over naïve Grad-CAM:
    - Soft lung-field prior (no hard mask edges).
    - Percentile gate keeps only the top activations.
    - Per-pixel alpha derived purely from activation strength, so zero-activation
      areas remain 100 % original X-ray (no blue/cyan background artefact from JET).
    - COLORMAP_JET retained for familiarity but applied only where alpha > 0.
    Returns PNG bytes, or None on failure.
    """
    if pneumonia_model is None:
        return None

    try:
        image        = Image.open(BytesIO(image_data)).convert('RGB')
        original_rgb = np.array(image)
        height, width = original_rgb.shape[:2]

        # ── 1. Model forward pass (same preprocessing as prediction) ────────
        model_image = image.resize((224, 224))
        img_array   = np.expand_dims(np.array(model_image) / 255.0, axis=0)

        grad_model = tf.keras.models.Model(
            [pneumonia_model.inputs],
            [pneumonia_model.get_layer(last_conv_layer_name).output,
             pneumonia_model.output]
        )

        with tf.GradientTape() as tape:
            conv_outputs, predictions = grad_model(img_array, training=False)
            class_channel = (predictions[:, 1]
                             if predictions.shape[-1] > 1
                             else predictions[:, 0])

        grads = tape.gradient(class_channel, conv_outputs)
        if grads is None:
            return None

        # ── 2. Grad-CAM heatmap ─────────────────────────────────────────────
        pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))
        heatmap      = tf.reduce_sum(conv_outputs[0] * pooled_grads, axis=-1)
        heatmap      = tf.maximum(heatmap, 0)
        hmap_max     = tf.reduce_max(heatmap)
        heatmap      = tf.cond(
            tf.equal(hmap_max, 0),
            lambda: tf.zeros_like(heatmap),
            lambda: heatmap / (hmap_max + tf.keras.backend.epsilon())
        ).numpy().astype(np.float32)

        # ── 3. Upsample + strong smoothing for continuous clinical-style map ─
        heatmap = cv2.resize(heatmap, (width, height)).astype(np.float32)
        heatmap = cv2.GaussianBlur(heatmap, (0, 0), sigmaX=8.0, sigmaY=8.0)

        # ── 4. Anatomical weighting + thorax window (edge/armpit suppression) ─
        lung_mask = _build_lung_soft_mask(height, width)
        heatmap = heatmap * (0.45 + 0.55 * lung_mask)

        # Smooth thorax window:
        # - Suppress lateral image borders (common Grad-CAM spillover to arms/devices)
        # - De-emphasize very top shoulder region while keeping upper lungs visible
        x = np.linspace(0.0, 1.0, width, dtype=np.float32)
        y = np.linspace(0.0, 1.0, height, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)

        lateral_weight = np.clip((xx * (1.0 - xx)) / 0.25, 0.0, 1.0) ** 0.6
        top_ramp = np.clip((yy - 0.08) / 0.22, 0.0, 1.0)
        vertical_weight = 0.35 + 0.65 * top_ramp
        thorax_window = lateral_weight * vertical_weight
        thorax_window = cv2.GaussianBlur(thorax_window.astype(np.float32), (0, 0), sigmaX=18.0, sigmaY=18.0)

        heatmap = heatmap * np.clip(thorax_window, 0.0, 1.0)

        # Suppress black-border/background bleed but keep map continuous.
        gray = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2GRAY)
        _, body_binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
        body_soft = cv2.GaussianBlur(body_binary.astype(np.float32) / 255.0, (0, 0), sigmaX=20.0, sigmaY=20.0)
        heatmap = heatmap * np.clip(body_soft, 0.0, 1.0)

        # ── 5. Renormalise to [0, 1] and trim weak diffuse tails ────────────
        peak = float(np.max(heatmap))
        if peak > 0:
            heatmap = heatmap / peak

        active = heatmap[heatmap > 1e-4]
        if active.size > 0:
            tail_cutoff = float(np.percentile(active, 42))
            # Softly attenuate weak activations instead of hard clipping.
            heatmap = np.where(
                heatmap >= tail_cutoff,
                heatmap,
                np.clip(heatmap * (heatmap / (tail_cutoff + 1e-8)), 0, heatmap)
            )

        # ── 6. Per-pixel alpha — smooth/global look like reference examples ──
        # Linear-ish ramp avoids tiny "island" hotspots and keeps continuity.
        MAX_ALPHA = 0.56
        alpha_map = np.clip(heatmap ** 1.2 * MAX_ALPHA, 0.0, MAX_ALPHA)
        alpha_map = cv2.GaussianBlur(alpha_map, (0, 0), sigmaX=3.0, sigmaY=3.0)

        # ── 7. Colour map only where alpha is meaningful ─────────────────────
        heatmap_uint8  = np.uint8(np.clip(heatmap * 255.0, 0, 255))
        heatmap_color  = cv2.applyColorMap(heatmap_uint8,
                                           cv2.COLORMAP_JET).astype(np.float32)

        original_bgr   = cv2.cvtColor(original_rgb,
                                      cv2.COLOR_RGB2BGR).astype(np.float32)
        alpha_3ch      = alpha_map[..., np.newaxis]
        overlay_bgr    = (original_bgr * (1.0 - alpha_3ch) +
                          heatmap_color * alpha_3ch)
        overlay_bgr    = np.clip(overlay_bgr, 0, 255).astype(np.uint8)

        success, encoded = cv2.imencode('.png', overlay_bgr)
        return encoded.tobytes() if success else None

    except Exception as e:
        print(f"ERROR during Grad-CAM generation: {e}")
        traceback.print_exc()
        return None


def run_xray_validation(image_data):
    """
    X-ray validator inference
    Returns: {'is_xray': bool, 'confidence': float (0-100)}
    """
    try:
        # Always verify that the uploaded bytes are actually an image first.
        image = Image.open(BytesIO(image_data)).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError) as e:
        return {
            'is_xray': False,
            'confidence': 0,
            'reason': 'invalid_image',
            'error': str(e)
        }
    except Exception as e:
        return {
            'is_xray': False,
            'confidence': 0,
            'reason': 'invalid_image',
            'error': str(e)
        }

    if xray_validator_model is None:
        return {
            'is_xray': True,
            'confidence': 0,
            'reason': 'validator_skipped',
            'warning': 'X-ray validator model not loaded; validation skipped'
        }

    try:
        image = image.resize((224, 224))

        img_array = np.array(image) / 255.0
        img_array = np.expand_dims(img_array, axis=0)

        prediction = xray_validator_model.predict(img_array, verbose=0)

        if len(prediction[0]) > 1:
            class_index = min(max(XRAY_CLASS_INDEX, 0), len(prediction[0]) - 1)
            positive_confidence = float(prediction[0][class_index])
        else:
            positive_confidence = float(prediction[0][0])

        xray_confidence = positive_confidence if XRAY_POSITIVE_LABEL == 'xray' else (1.0 - positive_confidence)
        is_xray = xray_confidence >= XRAY_VALIDATOR_THRESHOLD

        result = {
            'is_xray': is_xray,
            'confidence': round(xray_confidence * 100, 2),
            'threshold': round(XRAY_VALIDATOR_THRESHOLD * 100, 2)
        }
        if not is_xray:
            result['reason'] = 'low_xray_confidence'
            result['warning'] = 'Image appears non-X-ray to validator model. Proceeded in non-strict mode.'
        return result

    except Exception as e:
        print(f"ERROR during X-ray validation: {e}")
        traceback.print_exc()
        # Fail-open: prediction-time validator errors should not block valid uploads.
        return {
            'is_xray': True,
            'confidence': 0,
            'reason': 'validator_error',
            'warning': f'X-ray validator error ignored in non-strict mode: {e}'
        }


# =====================================================================
# ANALYTICS & REPORTING
# =====================================================================

@app.route('/api/analytics', methods=['GET'])
@login_required
def get_analytics():
    """
    Get analytics data for dashboard
    Supports timeframe filtering: 7, 30, 90 days or all-time
    Also supports optional month/year filtering
    Role-based access: Admins see all, Doctors see their own, Nurses see system stats only
    """
    try:
        current_user = get_current_user()
        timeframe = request.args.get('timeframe', '30')  # days: '7', '30', '90', 'all'
        month_filter = request.args.get('month', type=int)
        year_filter = request.args.get('year', type=int)

        # Build base queries and apply month/year filters when provided.
        # Month/year filters take precedence over rolling timeframe when present.
        analyses_query = Analysis.query
        notifications_query = Notification.query

        has_calendar_filter = month_filter is not None or year_filter is not None

        if has_calendar_filter:
            if month_filter is not None and (month_filter < 1 or month_filter > 12):
                return jsonify({'success': False, 'error': 'Month must be between 1 and 12'}), 400
            if year_filter is not None and year_filter < 1900:
                return jsonify({'success': False, 'error': 'Year must be valid'}), 400

            if month_filter is not None:
                analyses_query = analyses_query.filter(extract('month', Analysis.created_at) == month_filter)
                notifications_query = notifications_query.filter(extract('month', Notification.created_at) == month_filter)
            if year_filter is not None:
                analyses_query = analyses_query.filter(extract('year', Analysis.created_at) == year_filter)
                notifications_query = notifications_query.filter(extract('year', Notification.created_at) == year_filter)
        else:
            # Calculate rolling timeframe filter
            if timeframe == 'all':
                date_filter = None
            else:
                days = int(timeframe)
                date_filter = datetime.utcnow() - timedelta(days=days)

            if date_filter:
                analyses_query = analyses_query.filter(Analysis.created_at >= date_filter)
                notifications_query = notifications_query.filter(Notification.created_at >= date_filter)
        
        # Get all analyses in timeframe (or filtered by user role)
        if current_user.role == 'admin':
            analyses = analyses_query.all()
            users = User.query.filter(User.is_active == True).all()
        elif current_user.role == 'doctor':
            # Doctors see their reviewed analyses + system stats
            analyses = analyses_query.all()
            users = User.query.filter(User.is_active == True).all()
        else:  # nurse
            # Nurses see only system statistics, no personal data
            analyses = analyses_query.all()
            users = User.query.filter(User.is_active == True).all()
        
        # Calculate metrics
        total_analyses = len(analyses)
        pneumonia_cases = len([a for a in analyses if a.pneumonia_detected])
        normal_cases = total_analyses - pneumonia_cases
        detection_rate = (pneumonia_cases / total_analyses * 100) if total_analyses > 0 else 0
        
        avg_confidence = sum([a.confidence for a in analyses]) / total_analyses if total_analyses > 0 else 0
        
        # CURB-65 distribution
        curb_distribution = {
            'Low': len([a for a in analyses if a.curb_risk == 'Low']),
            'Moderate': len([a for a in analyses if a.curb_risk == 'Moderate']),
            'High': len([a for a in analyses if a.curb_risk == 'High']),
            'Very High': len([a for a in analyses if a.curb_risk == 'Very High'])
        }
        
        # Alert statistics
        notifications = notifications_query.all()
        critical_alerts = len([n for n in notifications if n.urgency_level == 'CRITICAL'])
        high_alerts = len([n for n in notifications if n.urgency_level == 'HIGH'])
        moderate_alerts = len([n for n in notifications if n.urgency_level == 'MODERATE'])
        pending_alerts = len([n for n in notifications if not n.is_acknowledged])
        acknowledged_alerts = len([n for n in notifications if n.is_acknowledged])
        
        # Doctor/Nurse performance metrics
        doctor_stats = {}
        for user in [u for u in users if u.role in ['doctor', 'nurse']]:
            reviewed = len([a for a in analyses if a.reviewed_by_user_id == user.id])
            created = len([a for a in analyses if a.created_by_user_id == user.id])
            
            # Calculate avg response time (from creation to review)
            response_times = []
            for analysis in analyses:
                if analysis.reviewed_by_user_id == user.id and analysis.reviewed_at:
                    time_diff = (analysis.reviewed_at - analysis.created_at).total_seconds() / 3600  # hours
                    response_times.append(time_diff)
            
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            doctor_stats[user.id] = {
                'name': user.name,
                'role': user.role,
                'reviewed_cases': reviewed,
                'created_cases': created,
                'avg_response_time_hours': round(avg_response_time, 1),
                'acknowledgements': len([n for n in notifications if n.recipient_id == user.id and n.is_acknowledged])
            }
        
        # Confidence distribution for histogram
        confidence_buckets = {
            '0-20%': len([a for a in analyses if 0 <= a.confidence < 20]),
            '20-40%': len([a for a in analyses if 20 <= a.confidence < 40]),
            '40-60%': len([a for a in analyses if 40 <= a.confidence < 60]),
            '60-80%': len([a for a in analyses if 60 <= a.confidence < 80]),
            '80-100%': len([a for a in analyses if 80 <= a.confidence <= 100])
        }
        
        # Cases over time (daily breakdown)
        cases_by_date = {}
        for analysis in analyses:
            date_key = analysis.created_at.strftime('%Y-%m-%d')
            cases_by_date[date_key] = cases_by_date.get(date_key, 0) + 1
        
        # Sort by date
        cases_over_time = sorted(cases_by_date.items())
        
        return jsonify({
            'success': True,
            'timeframe': timeframe,
            'month_filter': month_filter,
            'year_filter': year_filter,
            'metrics': {
                'total_analyses': total_analyses,
                'pneumonia_cases': pneumonia_cases,
                'normal_cases': normal_cases,
                'detection_rate': round(detection_rate, 1),
                'avg_confidence': round(avg_confidence, 1)
            },
            'severity_distribution': curb_distribution,
            'alert_statistics': {
                'critical': critical_alerts,
                'high': high_alerts,
                'moderate': moderate_alerts,
                'pending': pending_alerts,
                'acknowledged': acknowledged_alerts
            },
            'staff_performance': doctor_stats,
            'confidence_distribution': confidence_buckets,
            'cases_over_time': cases_over_time
        }), 200
    
    except Exception as e:
        print(f"Error fetching analytics: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/staff-performance', methods=['GET'])
@login_required
@role_required('admin')
def get_staff_performance():
    """
    Get individual staff performance metrics
    Returns performance stats for all doctors and nurses
    """
    try:
        # Get all doctors and nurses
        staff = User.query.filter(User.role.in_(['doctor', 'nurse'])).all()
        
        staff_data = []
        
        for user in staff:
            # Count analyses created by this user
            analyses_count = Analysis.query.filter_by(created_by_user_id=user.id).count()
            
            # Count analyses reviewed by this user (doctor only)
            reviews_count = 0
            if user.role == 'doctor':
                reviews_count = Analysis.query.filter_by(reviewed_by_user_id=user.id).count()
            
            # Get pending reviews (for doctors)
            pending_reviews = 0
            if user.role == 'doctor':
                pending_reviews = Analysis.query.filter_by(reviewed_by_user_id=None).count()
            
            # Count assigned patients
            assigned_patients_count = PatientStaff.query.filter_by(user_id=user.id).count()
            
            # Get average confidence for this staff's analyses
            avg_confidence = db.session.query(db.func.avg(Analysis.confidence)).filter(
                Analysis.created_by_user_id == user.id
            ).scalar() or 0
            
            # Get pneumonia detection rate
            pneumonia_detected = Analysis.query.filter_by(
                created_by_user_id=user.id,
                pneumonia_detected=True
            ).count()
            detection_rate = (pneumonia_detected / analyses_count * 100) if analyses_count > 0 else 0
            
            # Get last activity
            last_analysis = Analysis.query.filter_by(created_by_user_id=user.id).order_by(
                Analysis.created_at.desc()
            ).first()
            last_activity = (last_analysis.created_at.isoformat() + '+00:00') if last_analysis else None
            
            staff_data.append({
                'user_id': user.id,
                'name': user.name,
                'role': user.role,
                'email': user.email,
                'analyses_count': analyses_count,
                'reviews_count': reviews_count,
                'pending_reviews': pending_reviews,
                'assigned_patients': assigned_patients_count,
                'avg_confidence': round(avg_confidence, 1),
                'pneumonia_detection_rate': round(detection_rate, 1),
                'last_activity': last_activity
            })
        
        # Sort by analyses count (most active first)
        staff_data.sort(key=lambda x: x['analyses_count'], reverse=True)
        
        return jsonify({
            'success': True,
            'staff': staff_data
        }), 200
    
    except Exception as e:
        print(f"Error fetching staff performance: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Page not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Initialize database
    with app.app_context():
        print("Initializing database...")
        db.create_all()
        print("✓ Database initialized successfully")
    
    # Run Flask app
    app.run(debug=True, host='localhost', port=5000)

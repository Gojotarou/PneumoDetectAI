"""
PneumoDetect Flask Application
Main backend server for medical X-ray analysis with Role-Based Access Control
"""

from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from werkzeug.utils import secure_filename
from functools import wraps
import os
import json
from datetime import datetime, timedelta
import base64
from io import BytesIO
import numpy as np
from PIL import Image
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image as keras_image
import tensorflow as tf
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from sqlalchemy import case
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

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+mysqlconnector://{os.getenv('MYSQL_USER')}:"
    f"{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST')}/"
    f"{os.getenv('MYSQL_DATABASE')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Initialize database tables and test accounts
init_db(app)

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
    return render_template('dashboard.html')

@app.route('/new_analysis.html')
@login_required
@role_required('doctor', 'nurse')
def new_analysis():
    return render_template('new_analysis.html')

@app.route('/new_analysis_upload.html')
@login_required
@role_required('nurse', 'doctor')
def new_analysis_upload():
    return render_template('new_analysis_upload.html')

@app.route('/results.html')
@login_required
def results():
    return render_template('results.html')

@app.route('/alerts.html')
@login_required
def alerts():
    return render_template('alerts.html')

@app.route('/report.html')
@login_required
@role_required('doctor', 'nurse', 'admin')
def report():
    return render_template('report.html')

@app.route('/management.html')
@login_required
@role_required('admin')
def management():
    return render_template('management.html')

@app.route('/upload.html')
@login_required
@role_required('nurse', 'doctor')
def upload():
    return render_template('upload.html')

@app.route('/curb65.html')
@login_required
def curb65():
    return render_template('curb65.html')

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
                'role': user.role
            })
        
        return jsonify({
            'success': True,
            'users': user_list
        }), 200
    
    except Exception as e:
        print(f"Error fetching users: {e}")
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
                'annotations': annotations_data
            }
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        print(f"Error fetching alert case: {e}")
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
        
        # Get clinical parameters from form
        age = int(request.form.get('age', 0))
        confusion = int(request.form.get('confusion', 0))
        urea = float(request.form.get('urea', 0))
        respiratory = float(request.form.get('respiratory', 0))
        sbp = float(request.form.get('sbp', 0))
        dbp = float(request.form.get('dbp', 0))
        patient_name = request.form.get('patient_name', 'Unknown')
        medical_id = request.form.get('medical_id', f"AUTO-{int(datetime.now().timestamp())}")
        
        # Get or create patient
        patient = Patient.query.filter_by(medical_id=medical_id).first()
        if not patient:
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
        
        # Compute CURB-65 score
        curb_score_data = compute_curb65(age, confusion, urea, respiratory, sbp, dbp)
        
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
        
        # Auto-assign the uploader to this patient if not already assigned
        user = get_current_user()
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
            'curb_score': curb_score_data,
            'image_url': f"/api/image/{analysis.id}"
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error in analyze_xray: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'PneumoDetect API'})


@app.route('/api/save-annotations', methods=['POST'])
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
        
        db.session.add(annotation)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Annotations saved successfully',
            'annotation_id': annotation.id
        }), 200
    
    except Exception as e:
        db.session.rollback()
        print(f"Error saving annotations: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-report', methods=['POST'])
@login_required
def download_report():
    """
    Generate and download a professional PDF report with X-ray image
    Expects JSON: analysis_id, patient_name, medical_id, age, pneumonia_detected, confidence, curb_score, annotations
    """
    try:
        data = request.get_json()
        analysis_id = data.get('analysis_id')
        
        # Retrieve analysis and image from database
        analysis = None
        if analysis_id:
            analysis = Analysis.query.get(analysis_id)
        
        # Create PDF in memory
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#0056b3'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#0056b3'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        
        # Header
        elements.append(Paragraph("MEDICAL ANALYSIS REPORT", title_style))
        elements.append(Paragraph("PneumoDetect AI Diagnostic System", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))
        
        # Patient Information Section
        elements.append(Paragraph("PATIENT INFORMATION", heading_style))
        patient_data = [
            ['Patient Name:', data.get('patient_name', 'N/A')],
            ['Medical ID:', data.get('medical_id', 'N/A')],
            ['Age:', str(data.get('age', 'N/A')) + ' years'],
            ['Report Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ]
        
        patient_table = Table(patient_data, colWidths=[1.5*inch, 4.5*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e9ecef')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        elements.append(patient_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # AI Diagnosis Section
        elements.append(Paragraph("AI DIAGNOSIS RESULTS", heading_style))
        pneumonia_status = "PNEUMONIA DETECTED" if data.get('pneumonia_detected') else "NORMAL"
        status_color = colors.HexColor('#dc3545') if data.get('pneumonia_detected') else colors.HexColor('#28a745')
        
        diagnosis_data = [
            ['Diagnosis Status:', pneumonia_status],
            ['Confidence Score:', f"{data.get('confidence', 0):.2f}%"],
            ['Analysis Method:', 'Convolutional Neural Network (CNN)'],
            ['Model Type:', 'Deep Learning - Medical Imaging']
        ]
        
        diagnosis_table = Table(diagnosis_data, colWidths=[1.5*inch, 4.5*inch])
        diagnosis_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e9ecef')),
            ('TEXTCOLOR', (1, 0), (1, 0), status_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 0), (1, 0), 12),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        elements.append(diagnosis_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # X-Ray Image Section
        if analysis and analysis.image_base64:
            elements.append(Paragraph("DIAGNOSTIC X-RAY IMAGE", heading_style))
            try:
                # Convert binary image data to PIL Image
                image_data = analysis.image_base64
                if isinstance(image_data, bytes):
                    img = Image.open(BytesIO(image_data))
                else:
                    img = Image.open(BytesIO(image_data.encode() if isinstance(image_data, str) else image_data))
                
                # Add image to PDF with proper sizing
                # Convert PIL Image to ReportLab Image
                img_buffer = BytesIO()
                img.save(img_buffer, format='PNG')
                img_buffer.seek(0)
                
                rl_image = RLImage(img_buffer, width=4.5*inch, height=3.5*inch)
                elements.append(rl_image)
                elements.append(Spacer(1, 0.2*inch))
                
                # Add caption
                elements.append(Paragraph(
                    "<i>Chest X-Ray Image for AI Diagnostic Analysis</i>",
                    ParagraphStyle(
                        'ImageCaption',
                        parent=styles['Normal'],
                        fontSize=9,
                        textColor=colors.HexColor('#666666'),
                        alignment=TA_CENTER
                    )
                ))
                elements.append(Spacer(1, 0.2*inch))
            except Exception as e:
                print(f"Warning: Could not add image to PDF: {e}")
                elements.append(Paragraph("<i>X-Ray image could not be embedded</i>", styles['Normal']))
                elements.append(Spacer(1, 0.2*inch))
        
        # CURB-65 Risk Assessment Section
        elements.append(Paragraph("SEVERITY ASSESSMENT (CURB-65 SCORE)", heading_style))
        curb_score_data = data.get('curb_score', {})
        risk_level = curb_score_data.get('risk', 'Unknown')
        risk_color = colors.HexColor('#dc3545') if risk_level == 'Severe' else (colors.HexColor('#ff9800') if risk_level == 'Moderate' else colors.HexColor('#28a745'))
        
        curb_data = [
            ['CURB-65 Score:', str(curb_score_data.get('score', 'N/A')) + '/5'],
            ['Risk Level:', risk_level],
            ['Clinical Significance:', 'Determines severity and hospitalization need']
        ]
        
        curb_table = Table(curb_data, colWidths=[1.5*inch, 4.5*inch])
        curb_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e9ecef')),
            ('TEXTCOLOR', (1, 1), (1, 1), risk_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 1), (1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 1), (1, 1), 12),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        elements.append(curb_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Doctor's Annotations Section
        annotations = data.get('annotations', {})
        if any([annotations.get('doctorName'), annotations.get('finalDiagnosis'), annotations.get('clinicalNotes'), 
                annotations.get('treatmentPlan'), annotations.get('followUpInstructions')]):
            elements.append(Paragraph("DOCTOR'S ANNOTATIONS AND RECOMMENDATIONS", heading_style))
            
            # Doctor info
            if annotations.get('doctorName'):
                elements.append(Paragraph(f"<b>Reviewing Physician:</b> {annotations.get('doctorName')}", styles['Normal']))
            
            # Final Diagnosis
            if annotations.get('finalDiagnosis'):
                elements.append(Spacer(1, 0.1*inch))
                elements.append(Paragraph(f"<b>Final Diagnosis:</b> {annotations.get('finalDiagnosis')}", styles['Normal']))
            
            # Clinical Notes
            if annotations.get('clinicalNotes'):
                elements.append(Spacer(1, 0.1*inch))
                elements.append(Paragraph("<b>Clinical Notes:</b>", styles['Normal']))
                elements.append(Paragraph(annotations.get('clinicalNotes'), ParagraphStyle(
                    'Notes',
                    parent=styles['Normal'],
                    fontSize=9,
                    textColor=colors.HexColor('#555555'),
                    leftIndent=12
                )))
            
            # Treatment Plan
            if annotations.get('treatmentPlan'):
                elements.append(Spacer(1, 0.1*inch))
                elements.append(Paragraph("<b>Treatment Plan:</b>", styles['Normal']))
                elements.append(Paragraph(annotations.get('treatmentPlan'), ParagraphStyle(
                    'Treatment',
                    parent=styles['Normal'],
                    fontSize=9,
                    textColor=colors.HexColor('#555555'),
                    leftIndent=12
                )))
            
            # Follow-up Instructions
            if annotations.get('followUpInstructions'):
                elements.append(Spacer(1, 0.1*inch))
                elements.append(Paragraph("<b>Follow-up Instructions:</b>", styles['Normal']))
                elements.append(Paragraph(annotations.get('followUpInstructions'), ParagraphStyle(
                    'FollowUp',
                    parent=styles['Normal'],
                    fontSize=9,
                    textColor=colors.HexColor('#555555'),
                    leftIndent=12
                )))
            
            elements.append(Spacer(1, 0.2*inch))
        
        # Disclaimer Section
        elements.append(Paragraph("DISCLAIMER", heading_style))
        disclaimer_text = """
        This report presents results generated by PneumoDetect AI, a computer-aided diagnostic system. 
        These results are intended to assist medical professionals in their clinical decision-making and should not be used as a substitute for professional medical judgment. 
        A qualified physician must review all findings and provide final clinical diagnosis and treatment recommendations.
        """
        elements.append(Paragraph(disclaimer_text, ParagraphStyle(
            'Disclaimer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            alignment=TA_JUSTIFY,
            spaceAfter=12
        )))
        
        # Footer
        footer_text = f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | PneumoDetect Medical AI Platform"
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph(footer_text, ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
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
        import traceback
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
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to retrieve image', 'details': str(e)}), 500


# =====================================================================
# HELPER FUNCTIONS - Business Logic
# =====================================================================

def compute_curb65(age, confusion, urea, respiratory, sbp, dbp):
    """
    CURB-65 Score Calculator
    Returns score (0-5) and risk level
    """
    score = 0
    if confusion == 1:
        score += 1
    if urea > 7:
        score += 1
    if respiratory >= 30:
        score += 1
    if sbp < 90 or dbp <= 60:
        score += 1
    if age >= 65:
        score += 1
    
    return {
        'score': score,
        'risk': get_risk_level(score)
    }


def get_risk_level(curb_score):
    """Map CURB-65 score to risk level"""
    if curb_score <= 1:
        return 'Low'
    elif curb_score == 2:
        return 'Moderate'
    else:
        return 'Severe'


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
        
        # DEBUG: Print model output to understand format
        print(f"DEBUG - Raw prediction: {prediction}")
        print(f"DEBUG - Prediction shape: {prediction.shape}")
        print(f"DEBUG - Prediction dtype: {prediction.dtype}")
        
        # Extract pneumonia confidence (assuming binary classification)
        # If model outputs [normal, pneumonia], take pneumonia probability
        if len(prediction[0]) > 1:
            # Binary classification: [normal_prob, pneumonia_prob]
            pneumonia_confidence = float(prediction[0][1]) * 100
            print(f"DEBUG - Multi-class output. Pneumonia prob (index 1): {prediction[0][1]}")
        else:
            # Single output: direct pneumonia probability
            pneumonia_confidence = float(prediction[0][0]) * 100
            print(f"DEBUG - Single output: {prediction[0][0]}")
        
        # Threshold for detection (adjust as needed)
        detected = pneumonia_confidence >= 50
        
        print(f"DEBUG - Final confidence: {pneumonia_confidence}%, Detected: {detected}")
        
        return {
            'detected': detected,
            'confidence': round(pneumonia_confidence, 2)
        }
        
    except Exception as e:
        print(f"ERROR during pneumonia detection: {e}")
        import traceback
        traceback.print_exc()
        return {
            'detected': False,
            'confidence': 0,
            'error': str(e)
        }


# =====================================================================
# ERROR HANDLERS
# =====================================================================

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

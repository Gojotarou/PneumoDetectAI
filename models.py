"""
PneumoDetect Database Models
Defines all database tables for patient data, analysis results, and annotations
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Text
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """User authentication table with role-based access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'doctor', 'nurse'
    department = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    assigned_patients = db.relationship('PatientStaff', backref='staff', lazy=True, foreign_keys='PatientStaff.user_id', cascade='all, delete-orphan')
    assignments_made = db.relationship('PatientStaff', foreign_keys='PatientStaff.assigned_by_user_id', backref='assigned_by', lazy=True)
    created_annotations = db.relationship('Annotation', backref='created_by_user', lazy=True, foreign_keys='Annotation.created_by_user_id')
    created_analyses = db.relationship('Analysis', backref='created_by_user', lazy=True, foreign_keys='Analysis.created_by_user_id')
    reviewed_analyses = db.relationship('Analysis', backref='reviewed_by_user', lazy=True, foreign_keys='Analysis.reviewed_by_user_id')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'role': self.role,
            'department': self.department,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PatientStaff(db.Model):
    """Junction table for many-to-many relationship between patients and staff"""
    __tablename__ = 'patient_staff'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role_type = db.Column(db.String(50), nullable=False)  # 'primary_doctor', 'secondary_doctor', 'assigned_nurse'
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # who assigned this
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    patient = db.relationship('Patient', backref='staff_assignments', lazy=True)



class Patient(db.Model):
    """Patient information table"""
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    medical_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    contact = db.Column(db.String(255))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    analyses = db.relationship('Analysis', backref='patient', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'medical_id': self.medical_id,
            'name': self.name,
            'age': self.age,
            'contact': self.contact,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Analysis(db.Model):
    """X-ray analysis results table"""
    __tablename__ = 'analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # Nurse who uploaded
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # Doctor who reviewed
    reviewed_at = db.Column(db.DateTime)  # When doctor reviewed
    
    # Clinical parameters (CURB-65)
    age = db.Column(db.Integer, nullable=False)
    confusion = db.Column(db.Integer, default=0)  # 0 or 1
    urea = db.Column(db.Float, default=0)
    respiratory_rate = db.Column(db.Float, default=0)
    systolic_bp = db.Column(db.Float, default=0)
    diastolic_bp = db.Column(db.Float, default=0)
    
    # CURB-65 Score
    curb_score = db.Column(db.Integer)
    curb_risk = db.Column(db.String(20))  # 'Low', 'Moderate', 'Severe'
    
    # AI Pneumonia Detection Results
    pneumonia_detected = db.Column(db.Boolean, default=False)
    confidence = db.Column(db.Float)  # 0-100
    
    # Image storage
    image_filename = db.Column(db.String(255))  # name of saved image file
    image_base64 = db.Column(db.LargeBinary)  # Store binary image data directly (more efficient than base64)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    annotations = db.relationship('Annotation', backref='analysis', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'pneumonia_detected': self.pneumonia_detected,
            'confidence': self.confidence,
            'curb_score': self.curb_score,
            'curb_risk': self.curb_risk,
            'patient_name': self.patient.name if self.patient else None,
            'medical_id': self.patient.medical_id if self.patient else None,
            'age': self.age,
            'timestamp': self.created_at.isoformat() if self.created_at else None,
            'image_url': f"/api/image/{self.id}" if self.image_base64 else None,
            'created_by': self.created_by_user.name if self.created_by_user else 'Unknown',
            'reviewed_by': self.reviewed_by_user.name if self.reviewed_by_user else None
        }


class Annotation(db.Model):
    """Doctor's clinical annotations for each analysis"""
    __tablename__ = 'annotations'
    
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analyses.id'), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # Which doctor created this
    
    # Doctor information
    doctor_name = db.Column(db.String(255))
    final_diagnosis = db.Column(db.String(255))
    
    # Clinical notes
    clinical_notes = db.Column(db.Text)
    treatment_plan = db.Column(db.Text)
    follow_up_instructions = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'doctor_name': self.doctor_name,
            'final_diagnosis': self.final_diagnosis,
            'clinical_notes': self.clinical_notes,
            'treatment_plan': self.treatment_plan,
            'follow_up_instructions': self.follow_up_instructions,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Notification(db.Model):
    """Real-time notifications between staff members (Phase 6)"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Who receives the notification
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Who sends the notification
    
    # Notification content
    notification_type = db.Column(db.String(50), nullable=False)  # e.g., 'request_action', 'case_ready', 'alert'
    message = db.Column(db.String(500), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))  # Optional: related patient
    analysis_id = db.Column(db.Integer, db.ForeignKey('analyses.id'))  # Optional: related analysis
    
    # Status
    is_read = db.Column(db.Boolean, default=False)
    is_dismissed = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    # Relationships
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_notifications', lazy=True)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_notifications', lazy=True)
    patient = db.relationship('Patient', backref='notifications', lazy=True)
    analysis = db.relationship('Analysis', backref='notifications', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'recipient_id': self.recipient_id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.name if self.sender else 'Unknown',
            'notification_type': self.notification_type,
            'message': self.message,
            'patient_id': self.patient_id,
            'patient_name': self.patient.name if self.patient else None,
            'analysis_id': self.analysis_id,
            'is_read': self.is_read,
            'is_dismissed': self.is_dismissed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None
        }


def init_db(app):
    """Initialize database with app context"""
    with app.app_context():
        db.create_all()
        print("✓ Database tables created successfully")
        
        # Create dummy test accounts if they don't exist
        if User.query.filter_by(email='admin@pneumodetect.com').first() is None:
            # Admin user
            admin = User(
                email='admin@pneumodetect.com',
                name='Administrator',
                role='admin',
                department='Administration',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            print("✓ Created Admin user: admin@pneumodetect.com / admin123")
        
        if User.query.filter_by(email='doctor@pneumodetect.com').first() is None:
            # Doctor user
            doctor = User(
                email='doctor@pneumodetect.com',
                name='Dr. Sarah Johnson',
                role='doctor',
                department='Pulmonology',
                is_active=True
            )
            doctor.set_password('doctor123')
            db.session.add(doctor)
            print("✓ Created Doctor user: doctor@pneumodetect.com / doctor123")
        
        if User.query.filter_by(email='nurse@pneumodetect.com').first() is None:
            # Nurse user
            nurse = User(
                email='nurse@pneumodetect.com',
                name='Nurse Emily',
                role='nurse',
                department='Radiology',
                is_active=True
            )
            nurse.set_password('nurse123')
            db.session.add(nurse)
            print("✓ Created Nurse user: nurse@pneumodetect.com / nurse123")
        
        db.session.commit()
        print("✓ Database initialization complete!")

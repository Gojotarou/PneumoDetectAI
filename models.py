"""
PneumoDetect Database Models
Defines all database tables for patient data, analysis results, and annotations
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Text
from datetime import datetime

db = SQLAlchemy()


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
    image_base64 = db.Column(Text)  # base64 encoded image for quick access
    
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
            'image_data': f"data:image/png;base64,{self.image_base64}" if self.image_base64 else None
        }


class Annotation(db.Model):
    """Doctor's clinical annotations for each analysis"""
    __tablename__ = 'annotations'
    
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analyses.id'), nullable=False)
    
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


def init_db(app):
    """Initialize database with app context"""
    with app.app_context():
        db.create_all()
        print("✓ Database tables created successfully")

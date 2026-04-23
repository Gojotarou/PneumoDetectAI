"""
Seed Dummy Data for PneumoDetect - Direct Database Access
Creates test data without importing the full Flask app
"""

import sys
import os
from datetime import datetime, timedelta
import base64
from dotenv import load_dotenv

# Load environment from .env file
load_dotenv()

# Get the directory path
DIR_PATH = r"c:\Users\user\Documents\UNIMAS Education\Sem 7\V"
sys.path.insert(0, DIR_PATH)

from flask import Flask
from models import db, User, Patient, Analysis, PatientStaff, Notification

# Create minimal Flask app for database operations
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+mysqlconnector://{os.getenv('MYSQL_USER')}:"
    f"{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST')}/"
    f"{os.getenv('MYSQL_DATABASE')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def seed_database():
    """Populate database with comprehensive dummy data"""
    with app.app_context():
        # Clear existing data (optional - comment out if you want to add to existing data)
        # db.drop_all()
        # db.create_all()
        
        print("\n" + "="*60)
        print("SEEDING DUMMY DATA FOR PNEUMODETECT")
        print("="*60)
        
        # =====================================================================
        # 1. CREATE MULTIPLE USERS FOR EACH ROLE
        # =====================================================================
        print("\n[1] Creating Users...")
        
        users_data = [
            # Admins
            {'email': 'admin@pneumodetect.com', 'name': 'Administrator', 'role': 'admin', 'dept': 'Administration'},
            {'email': 'admin2@pneumodetect.com', 'name': 'Super Admin', 'role': 'admin', 'dept': 'IT Department'},
            
            # Doctors
            {'email': 'doctor@pneumodetect.com', 'name': 'Dr. Sarah Johnson', 'role': 'doctor', 'dept': 'Pulmonology'},
            {'email': 'dr.smith@pneumodetect.com', 'name': 'Dr. Michael Smith', 'role': 'doctor', 'dept': 'Radiology'},
            {'email': 'dr.lim@pneumodetect.com', 'name': 'Dr. Lim Wei Chen', 'role': 'doctor', 'dept': 'Internal Medicine'},
            
            # Nurses
            {'email': 'nurse@pneumodetect.com', 'name': 'Nurse Emily', 'role': 'nurse', 'dept': 'Radiology'},
            {'email': 'nurse.lisa@pneumodetect.com', 'name': 'Nurse Lisa Wong', 'role': 'nurse', 'dept': 'Radiology'},
            {'email': 'nurse.james@pneumodetect.com', 'name': 'James Nurse', 'role': 'nurse', 'dept': 'Emergency'},
        ]
        
        created_users = {}
        for user_data in users_data:
            user = User.query.filter_by(email=user_data['email']).first()
            if not user:
                user = User(
                    email=user_data['email'],
                    name=user_data['name'],
                    role=user_data['role'],
                    department=user_data['dept'],
                    is_active=True
                )
                user.set_password('password123')  # All test accounts use same password
                db.session.add(user)
                print(f"  ✓ Created {user_data['role'].upper()}: {user_data['name']}")
            
            created_users[user_data['email']] = user
        
        db.session.commit()
        
        # =====================================================================
        # 2. CREATE PATIENT DATA
        # =====================================================================
        print("\n[2] Creating Patients...")
        
        patients_data = [
            {'medical_id': 'P001', 'name': 'Ahmad Bin Hassan', 'age': 45, 'contact': '601-2345-6789'},
            {'medical_id': 'P002', 'name': 'Maria Garcia', 'age': 62, 'contact': '601-9876-5432'},
            {'medical_id': 'P003', 'name': 'David Wong', 'age': 38, 'contact': '601-5555-5555'},
            {'medical_id': 'P004', 'name': 'Fatima Khaled', 'age': 71, 'contact': '601-1111-2222'},
            {'medical_id': 'P005', 'name': 'John Smith', 'age': 55, 'contact': '601-3333-4444'},
            {'medical_id': 'P006', 'name': 'Lisa Chen', 'age': 48, 'contact': '601-7777-8888'},
            {'medical_id': 'P007', 'name': 'Robert Brown', 'age': 67, 'contact': '601-2222-3333'},
            {'medical_id': 'P008', 'name': 'Nurul Islam', 'age': 42, 'contact': '601-6666-7777'},
        ]
        
        created_patients = {}
        for patient_data in patients_data:
            patient = Patient.query.filter_by(medical_id=patient_data['medical_id']).first()
            if not patient:
                patient = Patient(
                    medical_id=patient_data['medical_id'],
                    name=patient_data['name'],
                    age=patient_data['age'],
                    contact=patient_data['contact'],
                    notes=f"Sample patient for testing"
                )
                db.session.add(patient)
                print(f"  ✓ Created Patient: {patient_data['name']} ({patient_data['medical_id']})")
            
            created_patients[patient_data['medical_id']] = patient
        
        db.session.commit()
        
        # =====================================================================
        # 3. ASSIGN PATIENTS TO DOCTORS & NURSES
        # =====================================================================
        print("\n[3] Assigning Patients to Staff...")
        
        # Get doctors and nurses
        doctor1 = created_users['doctor@pneumodetect.com']
        doctor2 = created_users['dr.smith@pneumodetect.com']
        nurse1 = created_users['nurse@pneumodetect.com']
        nurse2 = created_users['nurse.lisa@pneumodetect.com']
        admin = created_users['admin@pneumodetect.com']
        
        assignments = [
            (created_patients['P001'], doctor1, 'primary_doctor'),
            (created_patients['P001'], nurse1, 'assigned_nurse'),
            (created_patients['P002'], doctor2, 'primary_doctor'),
            (created_patients['P002'], nurse2, 'assigned_nurse'),
            (created_patients['P003'], doctor1, 'primary_doctor'),
            (created_patients['P003'], nurse1, 'assigned_nurse'),
            (created_patients['P004'], doctor2, 'primary_doctor'),
            (created_patients['P005'], doctor1, 'primary_doctor'),
            (created_patients['P005'], nurse2, 'assigned_nurse'),
            (created_patients['P006'], doctor2, 'primary_doctor'),
            (created_patients['P006'], nurse1, 'assigned_nurse'),
            (created_patients['P007'], doctor1, 'primary_doctor'),
            (created_patients['P008'], doctor2, 'primary_doctor'),
            (created_patients['P008'], nurse2, 'assigned_nurse'),
        ]
        
        for patient, staff, role_type in assignments:
            # Check if assignment already exists
            existing = PatientStaff.query.filter_by(
                patient_id=patient.id,
                user_id=staff.id,
                role_type=role_type
            ).first()
            
            if not existing:
                assignment = PatientStaff(
                    patient_id=patient.id,
                    user_id=staff.id,
                    role_type=role_type,
                    assigned_by_user_id=admin.id
                )
                db.session.add(assignment)
                print(f"  ✓ Assigned {patient.name} → {staff.name} ({role_type})")
        
        db.session.commit()
        
        # =====================================================================
        # 4. CREATE ANALYSIS DATA (X-ray results)
        # =====================================================================
        print("\n[4] Creating Analysis Records...")
        
        # Create a simple dummy image (1x1 pixel PNG in base64)
        dummy_image = base64.b64encode(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        ).decode('utf-8')
        
        analyses_data = [
            # Patient P001 - Ahmad (45 years old)
            {
                'patient': created_patients['P001'],
                'age': 45,
                'pneumonia': True,
                'confidence': 87.5,
                'confusion': 0,
                'urea': 8.2,
                'rr': 24,
                'sys_bp': 135,
                'dia_bp': 85,
                'created_by': nurse1,
                'reviewed_by': doctor1,
                'days_ago': 2
            },
            # Patient P002 - Maria (62 years old)
            {
                'patient': created_patients['P002'],
                'age': 62,
                'pneumonia': True,
                'confidence': 92.3,
                'confusion': 1,
                'urea': 9.5,
                'rr': 28,
                'sys_bp': 142,
                'dia_bp': 88,
                'created_by': nurse2,
                'reviewed_by': doctor2,
                'days_ago': 5
            },
            # Patient P003 - David (38 years old)
            {
                'patient': created_patients['P003'],
                'age': 38,
                'pneumonia': False,
                'confidence': 12.1,
                'confusion': 0,
                'urea': 6.1,
                'rr': 18,
                'sys_bp': 128,
                'dia_bp': 82,
                'created_by': nurse1,
                'reviewed_by': doctor1,
                'days_ago': 7
            },
            # Patient P004 - Fatima (71 years old)
            {
                'patient': created_patients['P004'],
                'age': 71,
                'pneumonia': True,
                'confidence': 78.9,
                'confusion': 1,
                'urea': 11.2,
                'rr': 26,
                'sys_bp': 138,
                'dia_bp': 84,
                'created_by': nurse2,
                'reviewed_by': doctor2,
                'days_ago': 1
            },
            # Patient P005 - John (55 years old)
            {
                'patient': created_patients['P005'],
                'age': 55,
                'pneumonia': False,
                'confidence': 8.5,
                'confusion': 0,
                'urea': 7.0,
                'rr': 20,
                'sys_bp': 132,
                'dia_bp': 83,
                'created_by': nurse2,
                'reviewed_by': doctor1,
                'days_ago': 3
            },
            # Patient P006 - Lisa (48 years old)
            {
                'patient': created_patients['P006'],
                'age': 48,
                'pneumonia': True,
                'confidence': 85.2,
                'confusion': 0,
                'urea': 7.8,
                'rr': 23,
                'sys_bp': 136,
                'dia_bp': 86,
                'created_by': nurse1,
                'reviewed_by': doctor2,
                'days_ago': 4
            },
            # Patient P007 - Robert (67 years old)
            {
                'patient': created_patients['P007'],
                'age': 67,
                'pneumonia': False,
                'confidence': 15.3,
                'confusion': 0,
                'urea': 8.9,
                'rr': 22,
                'sys_bp': 140,
                'dia_bp': 87,
                'created_by': nurse1,
                'reviewed_by': doctor1,
                'days_ago': 6
            },
            # Patient P008 - Nurul (42 years old)
            {
                'patient': created_patients['P008'],
                'age': 42,
                'pneumonia': True,
                'confidence': 89.7,
                'confusion': 0,
                'urea': 6.5,
                'rr': 25,
                'sys_bp': 130,
                'dia_bp': 81,
                'created_by': nurse2,
                'reviewed_by': doctor2,
                'days_ago': 0
            },
        ]
        
        # CURB-65 Risk Calculation
        def calculate_curb65(age, confusion, urea, rr, sys_bp):
            score = 0
            if age >= 65: score += 1
            if confusion == 1: score += 1
            if urea > 7: score += 1
            if rr >= 30: score += 1
            if sys_bp < 90: score += 1
            
            if score <= 1:
                risk = 'Low'
            elif score == 2:
                risk = 'Moderate'
            else:
                risk = 'Severe'
            
            return score, risk
        
        for analysis_data in analyses_data:
            # Check if analysis already exists
            existing = Analysis.query.filter_by(
                patient_id=analysis_data['patient'].id
            ).first()
            
            if not existing:
                curb_score, curb_risk = calculate_curb65(
                    analysis_data['age'],
                    analysis_data['confusion'],
                    analysis_data['urea'],
                    analysis_data['rr'],
                    analysis_data['sys_bp']
                )
                
                analysis = Analysis(
                    patient_id=analysis_data['patient'].id,
                    created_by_user_id=analysis_data['created_by'].id,
                    reviewed_by_user_id=analysis_data['reviewed_by'].id,
                    age=analysis_data['age'],
                    confusion=analysis_data['confusion'],
                    urea=analysis_data['urea'],
                    respiratory_rate=analysis_data['rr'],
                    systolic_bp=analysis_data['sys_bp'],
                    diastolic_bp=analysis_data['dia_bp'],
                    curb_score=curb_score,
                    curb_risk=curb_risk,
                    pneumonia_detected=analysis_data['pneumonia'],
                    confidence=analysis_data['confidence'],
                    image_base64=dummy_image,
                    created_at=datetime.utcnow() - timedelta(days=analysis_data['days_ago']),
                    reviewed_at=datetime.utcnow() - timedelta(days=analysis_data['days_ago']-1)
                )
                db.session.add(analysis)
                
                status = "PNEUMONIA POSITIVE" if analysis_data['pneumonia'] else "NORMAL"
                print(f"  ✓ Analysis for {analysis_data['patient'].name}: {status} ({analysis_data['confidence']}%)")
        
        db.session.commit()
        
        # =====================================================================
        # 5. CREATE NOTIFICATIONS
        # =====================================================================
        print("\n[5] Creating Notifications...")
        
        notifications_data = [
            {'sender': admin, 'recipient': doctor1, 'notif_type': 'assignment', 'message': 'You have been assigned 2 new patients'},
            {'sender': doctor1, 'recipient': nurse1, 'notif_type': 'request_action', 'message': 'Please review the X-ray for patient Ahmad'},
            {'sender': admin, 'recipient': doctor2, 'notif_type': 'alert', 'message': 'System maintenance scheduled for tonight'},
        ]
        
        for notif_data in notifications_data:
            # Check if notification exists
            existing = Notification.query.filter_by(
                sender_id=notif_data['sender'].id,
                recipient_id=notif_data['recipient'].id,
                message=notif_data['message']
            ).first()
            
            if not existing:
                notification = Notification(
                    sender_id=notif_data['sender'].id,
                    recipient_id=notif_data['recipient'].id,
                    notification_type=notif_data['notif_type'],
                    message=notif_data['message']
                )
                db.session.add(notification)
                print(f"  ✓ Created notification: {notif_data['message'][:40]}...")
        
        db.session.commit()
        
        # =====================================================================
        # SUMMARY
        # =====================================================================
        print("\n" + "="*60)
        print("✓ DUMMY DATA SEEDING COMPLETE!")
        print("="*60)
        
        print("\n📋 TEST ACCOUNTS CREATED:")
        print("\n  ADMIN ACCOUNTS:")
        print("    • admin@pneumodetect.com / password123")
        print("    • admin2@pneumodetect.com / password123")
        print("\n  DOCTOR ACCOUNTS:")
        print("    • doctor@pneumodetect.com / password123")
        print("    • dr.smith@pneumodetect.com / password123")
        print("    • dr.lim@pneumodetect.com / password123")
        print("\n  NURSE ACCOUNTS:")
        print("    • nurse@pneumodetect.com / password123")
        print("    • nurse.lisa@pneumodetect.com / password123")
        print("    • nurse.james@pneumodetect.com / password123")
        
        print("\n📊 DATA CREATED:")
        print(f"    • {len(created_patients)} Patients")
        print(f"    • {len(analyses_data)} Analysis Records")
        print(f"    • {len(assignments)} Patient-Staff Assignments")
        print(f"    • {len(notifications_data)} Notifications")
        
        print("\n🎯 HOW TO TEST BY ROLE:")
        print("\n  ADMIN:")
        print("    - Can see ALL patients and analyses")
        print("    - Can manage users, assign patients")
        print("    - Access to Training & Reports")
        print("\n  DOCTOR:")
        print("    - Can see ONLY assigned patients")
        print("    - Can review analyses and provide feedback")
        print("    - Can see reports and patient history")
        print("\n  NURSE:")
        print("    - Can see ONLY assigned patients")
        print("    - Can upload X-rays and create analyses")
        print("    - Can access Patient History")
        
        print("\n" + "="*60 + "\n")

if __name__ == '__main__':
    seed_database()

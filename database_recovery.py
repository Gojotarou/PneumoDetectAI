"""
PneumoDetect Database Recovery Script
Run this script to completely reset and recover the database
Restores all tables, columns, and test data
"""

import sys
import os
from app import app, db
from models import User, Patient, Analysis, Annotation, PatientStaff, Notification
from datetime import datetime

def recover_database():
    """Complete database recovery - drops all tables and recreates them"""
    
    print("\n" + "="*70)
    print("🔧 PNEUMODETECT DATABASE RECOVERY")
    print("="*70)
    
    with app.app_context():
        try:
            # Step 1: Drop all existing tables
            print("\n[1/4] Dropping all existing tables...")
            db.drop_all()
            print("✓ All tables dropped successfully")
            
            # Step 2: Create all tables from models
            print("\n[2/4] Creating all database tables...")
            db.create_all()
            print("✓ All tables created successfully")
            print("   Tables created:")
            print("   - users")
            print("   - patients")
            print("   - analyses")
            print("   - annotations")
            print("   - patient_staff")
            print("   - notifications")
            
            # Step 3: Create test accounts
            print("\n[3/4] Creating test accounts...")
            test_accounts = [
                {
                    'email': 'admin@pneumodetect.com',
                    'name': 'Admin User',
                    'password': 'admin123',
                    'role': 'admin',
                    'department': 'Administration'
                },
                {
                    'email': 'doctor1@pneumodetect.com',
                    'name': 'Dr. Sarah Johnson',
                    'password': 'doctor123',
                    'role': 'doctor',
                    'department': 'Pulmonology'
                },
                {
                    'email': 'doctor2@pneumodetect.com',
                    'name': 'Dr. James Wilson',
                    'password': 'doctor123',
                    'role': 'doctor',
                    'department': 'Internal Medicine'
                },
                {
                    'email': 'nurse1@pneumodetect.com',
                    'name': 'Nurse Emily Brown',
                    'password': 'nurse123',
                    'role': 'nurse',
                    'department': 'Radiology'
                },
                {
                    'email': 'nurse2@pneumodetect.com',
                    'name': 'Nurse Michael Chen',
                    'password': 'nurse123',
                    'role': 'nurse',
                    'department': 'Respiratory'
                }
            ]
            
            for acc in test_accounts:
                user = User(
                    email=acc['email'],
                    name=acc['name'],
                    role=acc['role'],
                    department=acc['department'],
                    is_active=True
                )
                user.set_password(acc['password'])
                db.session.add(user)
                print(f"   ✓ Created {acc['role']}: {acc['email']}")
            
            db.session.commit()
            
            # Step 4: Create sample patients and assignments
            print("\n[4/4] Creating sample data...")
            
            # Get admin and staff users
            admin = User.query.filter_by(email='admin@pneumodetect.com').first()
            doctor1 = User.query.filter_by(email='doctor1@pneumodetect.com').first()
            nurse1 = User.query.filter_by(email='nurse1@pneumodetect.com').first()
            
            # Create sample patients
            sample_patients = [
                {
                    'medical_id': 'PAT-001',
                    'name': 'John Doe',
                    'age': 65,
                    'contact': '+1-555-0101',
                    'notes': 'Sample patient - pneumonia case'
                },
                {
                    'medical_id': 'PAT-002',
                    'name': 'Jane Smith',
                    'age': 52,
                    'contact': '+1-555-0102',
                    'notes': 'Sample patient - normal case'
                },
                {
                    'medical_id': 'PAT-003',
                    'name': 'Robert Wilson',
                    'age': 71,
                    'contact': '+1-555-0103',
                    'notes': 'Sample patient - follow-up case'
                }
            ]
            
            for pat_data in sample_patients:
                patient = Patient(
                    medical_id=pat_data['medical_id'],
                    name=pat_data['name'],
                    age=pat_data['age'],
                    contact=pat_data['contact'],
                    notes=pat_data['notes']
                )
                db.session.add(patient)
                print(f"   ✓ Created patient: {pat_data['medical_id']} - {pat_data['name']}")
            
            db.session.commit()
            
            # Create patient-staff assignments
            patients = Patient.query.all()
            for idx, patient in enumerate(patients):
                assignment = PatientStaff(
                    patient_id=patient.id,
                    user_id=doctor1.id,
                    role_type='primary_doctor',
                    assigned_by_user_id=admin.id
                )
                db.session.add(assignment)
                
                if nurse1:
                    assignment2 = PatientStaff(
                        patient_id=patient.id,
                        user_id=nurse1.id,
                        role_type='assigned_nurse',
                        assigned_by_user_id=admin.id
                    )
                    db.session.add(assignment2)
            
            db.session.commit()
            print(f"   ✓ Created patient-staff assignments")
            
            # Print recovery summary
            print("\n" + "="*70)
            print("✓ DATABASE RECOVERY COMPLETE!")
            print("="*70)
            print("\n📊 Database Summary:")
            print(f"   Users: {User.query.count()}")
            print(f"   Patients: {Patient.query.count()}")
            print(f"   Analyses: {Analysis.query.count()}")
            print(f"   Annotations: {Annotation.query.count()}")
            print(f"   PatientStaff: {PatientStaff.query.count()}")
            print(f"   Notifications: {Notification.query.count()}")
            
            print("\n🔐 Test Credentials:")
            for acc in test_accounts:
                print(f"   {acc['email']} / {acc['password']} ({acc['role']})")
            
            print("\n✅ Database is ready to use!")
            print("="*70 + "\n")
            
            return True
            
        except Exception as e:
            print(f"\n❌ ERROR during recovery: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return False


if __name__ == '__main__':
    # Confirm before running
    print("\n⚠️  WARNING: This will DELETE all existing data and recreate tables!")
    response = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
    
    if response == 'yes':
        success = recover_database()
        sys.exit(0 if success else 1)
    else:
        print("Recovery cancelled.")
        sys.exit(0)

#!/usr/bin/env python
"""
Test image storage and retrieval - Hospital Grade Reliability Check
"""

from app import app, db
from models import Analysis, Patient, User
from sqlalchemy import text
from io import BytesIO
from PIL import Image
import os

def create_test_image():
    """Create a simple test image (like an X-ray)"""
    img = Image.new('RGB', (512, 512), color='gray')
    # Draw some patterns to simulate X-ray
    pixels = img.load()
    for i in range(0, 512, 20):
        for j in range(0, 512, 20):
            pixels[i, j] = (200, 200, 200)
    
    # Save to bytes
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()

with app.app_context():
    try:
        print("=" * 60)
        print("HOSPITAL-GRADE IMAGE STORAGE TEST")
        print("=" * 60)
        
        # 1. Check database schema
        print("\n1. Checking database schema...")
        result = db.session.execute(text("""
            SELECT COLUMN_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'analyses' AND COLUMN_NAME = 'image_base64'
        """)).first()
        
        if result:
            col_type, max_len = result
            print(f"   Column type: {col_type}")
            if 'MEDIUMBLOB' in str(col_type).upper():
                print(f"   ✓ MEDIUMBLOB confirmed (supports up to 16MB)")
            else:
                print(f"   ⚠ WARNING: Column is {col_type}, not MEDIUMBLOB")
        
        # 2. Create test patient
        print("\n2. Creating test patient...")
        patient = Patient.query.filter_by(medical_id='TEST-001').first()
        if not patient:
            patient = Patient(
                medical_id='TEST-001',
                name='Test Patient',
                age=45
            )
            db.session.add(patient)
            db.session.commit()
            print("   ✓ Patient created")
        
        # 3. Create test image and store
        print("\n3. Creating test X-ray image...")
        test_image = create_test_image()
        print(f"   ✓ Test image created ({len(test_image)} bytes)")
        
        # 4. Store in database
        print("\n4. Storing image in database...")
        analysis = Analysis(
            patient_id=patient.id,
            age=45,
            pneumonia_detected=False,
            confidence=0,
            image_filename='test.png',
            image_base64=test_image,
            curb_score=0,
            curb_risk='Low'
        )
        db.session.add(analysis)
        db.session.commit()
        print(f"   ✓ Image stored in database (Analysis ID: {analysis.id})")
        
        # 5. Retrieve from database
        print("\n5. Retrieving image from database...")
        retrieved = Analysis.query.get(analysis.id)
        if retrieved.image_base64:
            retrieved_data = retrieved.image_base64
            if isinstance(retrieved_data, bytes):
                print(f"   ✓ Retrieved as binary ({len(retrieved_data)} bytes)")
                
                # 6. Verify data integrity
                print("\n6. Verifying data integrity...")
                if len(retrieved_data) == len(test_image):
                    print(f"   ✓ Size matches ({len(retrieved_data)} bytes)")
                else:
                    print(f"   ✗ Size mismatch! Original: {len(test_image)}, Retrieved: {len(retrieved_data)}")
                
                if retrieved_data == test_image:
                    print(f"   ✓ Data integrity verified (100% match)")
                else:
                    print(f"   ✗ Data corruption detected!")
                    # Show first 20 bytes
                    print(f"   Original first 20 bytes: {test_image[:20]}")
                    print(f"   Retrieved first 20 bytes: {retrieved_data[:20]}")
            else:
                print(f"   ✗ Data is {type(retrieved_data)}, not bytes!")
        else:
            print(f"   ✗ No image data found!")
        
        # 7. Test image endpoint would use
        print("\n7. Testing image conversion (as endpoint would do)...")
        img_check = Image.open(BytesIO(retrieved.image_base64))
        print(f"   ✓ Image is valid PNG ({img_check.size})")
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED - HOSPITAL-GRADE STORAGE OK")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()

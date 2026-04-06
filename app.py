"""
PneumoDetect Flask Application
Main backend server for medical X-ray analysis
"""

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
import base64
from io import BytesIO
import numpy as np
from PIL import Image
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image as keras_image
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from models import db, Patient, Analysis, Annotation, init_db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
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

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
# ROUTES - Serve HTML Pages
# =====================================================================

@app.route('/')
@app.route('/dashboard.html')
def dashboard():
    return render_template('dashboard.html')

@app.route('/login.html')
def login():
    return render_template('login.html')

@app.route('/new_analysis.html')
def new_analysis():
    return render_template('new_analysis.html')

@app.route('/new_analysis_upload.html')
def new_analysis_upload():
    return render_template('new_analysis_upload.html')

@app.route('/results.html')
def results():
    return render_template('results.html')

@app.route('/alerts.html')
def alerts():
    return render_template('alerts.html')

@app.route('/report.html')
def report():
    return render_template('report.html')

@app.route('/training.html')
def training():
    return render_template('training.html')

@app.route('/upload.html')
def upload():
    return render_template('upload.html')

@app.route('/curb65.html')
def curb65():
    return render_template('curb65.html')

# =====================================================================
# API ENDPOINTS - Backend Logic
# =====================================================================

@app.route('/api/patient-records', methods=['GET'])
def get_patient_records():
    """
    Get all patient records from database
    Returns: {'success': bool, 'records': list of patient analysis records}
    """
    try:
        # Query all analyses sorted by creation date (newest first)
        analyses = Analysis.query.order_by(Analysis.created_at.desc()).all()
        
        records = []
        for analysis in analyses:
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
                'image_data': f"data:image/png;base64,{analysis.image_base64}" if analysis.image_base64 else None
            })
        
        return jsonify({
            'success': True,
            'records': records
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
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
        
        # Read image file and encode as base64 for storage
        file_data = file.read()
        image_b64 = base64.b64encode(file_data).decode('utf-8')
        
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
        
        # Save analysis to database
        analysis = Analysis(
            patient_id=patient.id,
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
            image_base64=image_b64
        )
        
        db.session.add(analysis)
        db.session.commit()
        
        # Prepare response
        response = {
            'success': True,
            'analysis_id': analysis.id,
            'timestamp': analysis.created_at.isoformat(),
            'patient_name': patient.name,
            'medical_id': patient.medical_id,
            'age': age,
            'pneumonia_detected': analysis.pneumonia_detected,
            'confidence': analysis.confidence,
            'curb_score': curb_score_data,
            'image_data': f"data:image/png;base64,{image_b64}"
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



def download_report():
    """
    Generate and download a professional PDF report
    Expects JSON: patient_name, medical_id, age, pneumonia_detected, confidence, curb_score
    """
    try:
        data = request.get_json()
        
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

# PneumoDetect - AI-Powered Pneumonia Detection System

A comprehensive medical AI platform for pneumonia detection using chest X-ray analysis, clinical severity assessment (CURB-65), multi-user management, alerts/notifications, and clinical workflow support.

## System Overview

PneumoDetect is a **role-based clinical decision support system** designed for:
- **Doctors/Radiologists**: Analyze chest X-rays with AI predictions, review alerts, generate PDF reports
- **Medical Staff**: Manage patient records, assign cases, track analysis history
- **Administrators**: User management, staff performance analytics, system oversight

## Project Structure

```
pneumodetect/
├── app.py                           # Main Flask application & API endpoints
├── models.py                        # Database models (SQLAlchemy ORM)
├── requirements.txt                 # Python dependencies
├── runtime.txt                      # Python version specification
├── Procfile                         # Deployment configuration
├── ENV_GUIDE.md                     # Environment variables documentation
├── .env                             # Local environment configuration
├── .python-version                  # Local Python version
├── .gitignore                       # Git ignore rules
│
├── templates/                       # HTML templates (Flask Jinja2)
│   ├── login.html                   # Authentication
│   ├── dashboard.html               # Main dashboard & patient list
│   ├── new_analysis.html            # Patient info entry form
│   ├── new_analysis_upload.html     # X-ray upload & CURB-65 input
│   ├── results.html                 # AI analysis results & severity score
│   ├── report.html                  # PDF report viewer & download
│   ├── alerts.html                  # Alert/notification management
│   ├── management.html              # Patient record management
│   ├── analytics.html               # System analytics & statistics
│   ├── staff_performance.html       # Staff performance metrics
│   ├── curb65.html                  # CURB-65 calculator tool
│   └── upload.html                  # Bulk upload interface
│
├── static/                          # Static assets
│   ├── css/
│   │   ├── style.css                # Main stylesheet
│   │   ├── dark-mode.css            # Dark mode theme
│   │   ├── alerts.css               # Alert styling
│   │   └── patient-history.css      # Patient history styles
│   ├── js/
│   │   └── mobile-nav.js            # Mobile navigation
│   └── images/                      # UI asset references (in archive/)
│
├── models/                          # ML models
│   ├── pneumonia_model.h5           # CNN model for pneumonia classification
│   └── xray_detector.h5             # X-ray validator (rejects non-medical images)
│
├── tools/                           # Utility scripts (non-runtime)
│   ├── database_recovery.py         # Database reset & initialization
│   ├── seed_dummy_data.py           # Test data generator
│   ├── test_pneumodetect_system.py  # System test suite
│   └── model_reporting_suite.py     # Model evaluation & metrics
│
├── archive/                         # Generated/archived content
│   ├── images/                      # UI Icon Images
│   └── report_outputs/              # Model evaluation reports
│
├── uploads/                         # Runtime user upload directory
│   └── (created automatically at runtime)
│
├── .venv/                           # Virtual environment
├── instance/                        # Flask instance folder
└── .vscode/                         # VS Code settings

```

## Quick Start

### Local Development

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Run the application:**
```bash
python app.py
```

The server starts at `http://localhost:5000`

**3. Access the application:**
- **Login page**: http://localhost:5000/login.html
- **Dashboard**: http://localhost:5000/dashboard.html
- **New Analysis**: http://localhost:5000/new_analysis_upload.html

### Production Deployment

**Requirements:**
- Python 3.11.9
- MySQL 5.7+ or MySQL Flexible Server (Azure)
- Gunicorn WSGI server

**Startup command (Heroku/Railway/Render):**
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```

**Startup command (Azure App Service):**
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300
```

## Core Features

### 1. **AI-Powered Pneumonia Detection**
- TensorFlow/Keras CNN model for chest X-ray analysis
- Confidence scoring (0-100%)
- **X-ray Validator**: Automatically rejects non-medical images in strict mode
- Prevents false positives from non-chest-X-ray uploads

### 2. **Clinical Severity Assessment (CURB-65)**
- Automatic scoring based on 5 clinical parameters:
  - **C**onfusion (yes/no)
  - **U**rea level (mmol/L)
  - **R**espiratory rate (breaths/min)
  - **B**lood pressure (systolic/diastolic mmHg)
  - **Age** (≥65 years)
- Risk classification: Low, Moderate, or Severe
- Combined with AI prediction for comprehensive assessment

### 3. **Alert & Notification System**
- Automatic alerts for severe cases (CURB-65 ≥3 or high pneumonia confidence)
- Real-time notifications for assigned staff
- Mark-as-read and dismiss functionality
- Role-based alert routing

### 4. **Multi-User Management & Role-Based Access Control**
- **Admin**: Full system access, user management, analytics
- **Doctor**: Analyze cases, view results, approve diagnoses
- **Medical Staff**: Manage patients, assign analyses, track history
- **Roles enforced** at route level with `@login_required` & `@role_required` decorators

### 5. **Patient Record Management**
- Patient demographics & medical ID tracking
- Complete analysis history per patient
- Doctor annotations & clinical notes
- Final diagnosis & treatment plan documentation

### 6. **Staff Performance Analytics**
- Case load tracking per staff member
- Analysis completion times
- Diagnostic accuracy metrics (if gold-standard data available)
- System-wide usage statistics

### 7. **Clinical Documentation**
- **PDF Report Generation**: Automatic export with patient info, AI results, severity score, and clinical notes
- **Doctor Annotations**: Add clinical observations and treatment plans to each analysis
- **Audit Trail**: All analyses timestamped and attributed to users

### 8. **Responsive Web Interface**
- Dashboard with recent cases & summary statistics
- Multi-step analysis workflow
- Mobile-friendly design with responsive CSS
- Dark mode support

## API Endpoints (Main)

### 1. **Authentication**
```
POST /api/login
  Request: {username, password}
  Response: {success, user_id, role}
  
POST /api/logout
  Response: {success}
```

### 2. **Main Analysis Workflow**
```
POST /api/analyze
  Upload chest X-ray + clinical parameters
  
  Content-Type: multipart/form-data
  Fields:
    - image (file): Chest X-ray image
    - age (int): Patient age
    - confusion (0|1): CURB-65 confusion score
    - urea (float): Serum urea (mmol/L)
    - respiratory (float): Respiratory rate (breaths/min)
    - sbp (float): Systolic blood pressure (mmHg)
    - dbp (float): Diastolic blood pressure (mmHg)
    - age_criterion (0|1): Age ≥65 years (CURB-65)
    - patient_name (string): Patient name
    - medical_id (string): Patient medical ID
  
  Response: {
    success: bool,
    pneumonia_detected: bool,
    confidence: float (0-100),
    curb_score: {score: int (0-5), risk: string},
    analysis_id: int,
    patient_name: string,
    age: int,
    medical_id: string,
    image_data: "data:image/png;base64,...",
    xray_validation: {is_xray: bool, confidence: float}
  }
```

### 3. **Alerts & Notifications**
```
GET /api/notifications
  Retrieve all notifications for current user
  
POST /api/notifications
  Create new notification/alert
  
PUT /api/notifications/<id>
  Mark notification as read
  
DELETE /api/notifications/<id>
  Dismiss notification
```

**Additional endpoints** for patient management, user CRUD, report generation, analytics are available (see `app.py` for complete list).

## Environment Configuration

See [ENV_GUIDE.md](ENV_GUIDE.md) for complete environment variable documentation.

**Key variables:**
```env
# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key

# Database (local development)
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=pneumodetect

# X-ray Validation
XRAY_VALIDATION_STRICT=true
XRAY_VALIDATOR_THRESHOLD=0.5
XRAY_POSITIVE_LABEL=xray

# Session
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=False  # Set to True in production with HTTPS
PERMANENT_SESSION_LIFETIME=86400  # seconds
```

## Deployment Platforms

PneumoDetect supports multiple deployment platforms with zero code changes:

### **Azure App Service + MySQL Flexible Server**
- Highest `TIMEOUT` value (300s) for longer processing
- Connection string from Azure dashboard
- Recommended for healthcare deployments

### **Heroku/Railway**
- Standard Procfile configuration
- MySQL add-on integration
- Scalable worker processes

### **Render**
- DATABASE_URL environment variable
- Full connection string format
- Free tier available

### **Local Development**
- XAMPP MySQL or local MySQL
- Flask development server
- `.env` file configuration

See [ENV_GUIDE.md](ENV_GUIDE.md) for platform-specific setup.

## Tools & Utilities

**Non-runtime scripts** in `tools/` folder:

- **`database_recovery.py`**: Reset database schema, create tables, initialize test accounts
- **`seed_dummy_data.py`**: Generate test patients & analyses for development/demo
- **`test_pneumodetect_system.py`**: Comprehensive system test suite (logins, API calls, database operations)
- **`model_reporting_suite.py`**: ML model evaluation (confusion matrix, ROC curve, classification report)

**Usage:**
```bash
# Reset database
python tools/database_recovery.py

# Populate with test data
python tools/seed_dummy_data.py

# Run system tests
python tools/test_pneumodetect_system.py

# Generate model reports
python tools/model_reporting_suite.py
```

## Database Schema

**Core tables:**
- `users` - System users (admin, doctor, staff)
- `patients` - Patient demographics & medical records
- `analysis` - Individual X-ray analyses with AI predictions
- `annotations` - Doctor clinical notes & diagnosis
- `notifications` - Alerts & system notifications
- `patient_staff` - Staff-patient assignments
- `xray_box_annotations` - Doctor-drawn annotations on X-rays
- `gradcam_box_annotations` - Grad-CAM interpretability markers (backend only)
- `gradcam_images` - Grad-CAM heatmap storage (backend only)
}
```

### GET `/api/health`
Health check endpoint.

```bash
curl http://localhost:5000/api/health
```

## Configuration

Edit `app.py` to modify:
- **Max file size**: `app.config['MAX_CONTENT_LENGTH']`
- **Upload folder**: `app.config['UPLOAD_FOLDER']`
- **Port**: Change `port=5000` in `app.run()`
- **Debug mode**: Change `debug=True` to `debug=False` for production

## Key Files

- **`app.py`**: Flask server with routes and API logic
- **`templates/new_analysis_upload.html`**: Frontend that calls `/api/analyze`
- **`templates/results.html`**: Results page that displays API response
- **`static/css/style.css`**: Shared stylesheet

## Next Steps

To enhance the application:

1. **Integrate Real ML Model**:
   - Replace the placeholder `run_pneumonia_detection()` in `app.py` with your actual TensorFlow/PyTorch model
   - Example: `model.predict(image_array)` for confidence score

2. **Add Database**:
   - Store analysis results in PostgreSQL or MongoDB
   - Keep patient history

3. **User Authentication**:
   - Add login/logout functionality with session management

4. **Production Deployment**:
   - Use Gunicorn instead of Flask dev server
   - Deploy to Heroku, AWS, or DigitalOcean

## Notes

- Images are stored as base64 data URLs in localStorage (fine for single uploads; use server storage for production)
- CURB-65 calculation is done both client-side (real-time feedback) and server-side (verification)
- Placeholder AI model uses rule-based logic; replace with actual ML model

---

**Created**: January 2026  
**Framework**: Flask 2.3.3  
**Python**: 3.7+

# PneumoDetect Flask Application

A medical AI platform for pneumonia detection using chest X-ray analysis with CURB-65 severity assessment.

## Project Structure

```
.
├── app.py                 # Flask application & API endpoints
├── requirements.txt       # Python dependencies
├── templates/             # HTML templates (Flask Jinja2)
│   ├── dashboard.html
│   ├── new_analysis.html
│   ├── new_analysis_upload.html
│   ├── results.html
│   ├── login.html
│   ├── report.html
│   ├── training.html
│   ├── upload.html
│   └── curb65.html
├── static/                # Static files (CSS, images)
│   ├── css/
│   │   └── style.css
│   └── images/
│       ├── dashboard.png
│       ├── upload.png
│       ├── history.png
│       └── alerts.png
└── uploads/               # Temporary upload folder

```

## Setup Instructions

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Flask Application

```bash
python app.py
```

The server will start at `http://localhost:5000`

### 3. Open in Browser

Navigate to:
- **Dashboard**: http://localhost:5000/
- **New Analysis**: http://localhost:5000/new_analysis_upload.html
- **Patient Info**: http://localhost:5000/new_analysis.html

## Features

- ✅ **Dashboard** - Overview of recent cases and statistics
- ✅ **New Analysis** - Multi-step workflow:
  - Step 1: Enter patient information
  - Step 2: Upload chest X-ray + CURB-65 clinical inputs
  - Step 3: View AI diagnosis and severity assessment
- ✅ **CURB-65 Calculator** - Automatic severity scoring based on clinical parameters
- ✅ **Image Preview** - Drag & drop or browse file upload with preview
- ✅ **AI Prediction** - Flask backend processes X-rays and returns predictions

## API Endpoints

### POST `/api/analyze`
Upload X-ray image and clinical parameters for analysis.

**Request:**
```
Content-Type: multipart/form-data

image: file
age: int
confusion: 0|1
urea: float
respiratory: float
sbp: float
dbp: float
patient_name: string
medical_id: string
```

**Response:**
```json
{
  "success": true,
  "pneumonia_detected": true,
  "confidence": 94.2,
  "curb_score": {
    "score": 3,
    "risk": "Severe"
  },
  "patient_name": "Chai Chan Sin Jin",
  "age": 24,
  "medical_id": "829932",
  "image_data": "data:image/png;base64,..."
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

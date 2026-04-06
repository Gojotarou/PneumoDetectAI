# Quick Start Guide

## Installation & Running (3 Steps)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start Flask Server
```bash
py app.py
```

You'll see:
```
 * Running on http://localhost:5000
 * Debug mode: on
```

### Step 3: Open Browser
Navigate to: **http://localhost:5000**

## Testing the Flow

1. **Dashboard** (http://localhost:5000/)
   - See stats and recent cases

2. **New Analysis** (http://localhost:5000/new_analysis.html)
   - Enter patient: "Chai Chan Sin Jin", Age: 24, ID: 829932
   - Click "Continue to X-Ray Upload"

3. **Upload X-Ray** (http://localhost:5000/new_analysis_upload.html)
   - Upload an image (any PNG/JPG)
   - Fill CURB-65 inputs:
     - Age: 24
     - Confusion: No
     - Urea: 5
     - Respiratory: 25
     - Systolic BP: 120
     - Diastolic BP: 80
   - Click "Analyze Patient"

4. **Results** (http://localhost:5000/results.html)
   - See uploaded image
   - View AI prediction
   - Check CURB-65 score

## Folder Layout (Where Files Go)

```
V/
├── app.py                    ← Flask server (RUN THIS)
├── requirements.txt          ← Dependencies
├── README.md                 ← Full docs
├── SETUP_COMPLETE.md         ← Setup info (this file)
│
├── templates/                ← HTML (Flask serves these)
│   ├── dashboard.html
│   ├── new_analysis.html
│   ├── new_analysis_upload.html
│   └── results.html
│
├── static/                   ← Images & CSS (Flask serves these)
│   ├── css/style.css
│   └── images/*.png
│
└── uploads/                  ← Uploaded files go here
```

## API Endpoint (For Developers)

**POST** `/api/analyze`

Send this from JavaScript:
```javascript
const formData = new FormData();
formData.append('image', fileInput.files[0]);
formData.append('age', '24');
formData.append('confusion', '0');
formData.append('urea', '5');
formData.append('respiratory', '25');
formData.append('sbp', '120');
formData.append('dbp', '80');
formData.append('patient_name', 'Chai Chan Sin Jin');
formData.append('medical_id', '829932');

const response = await fetch('/api/analyze', {
    method: 'POST',
    body: formData
});
const result = await response.json();
```

## Stopping the Server

Press `Ctrl + C` in the terminal

## File Changes Made

### Minimal HTML Changes
- `<link rel="stylesheet" href="style.css">` → `href="{{ url_for('static', filename='css/style.css') }}"`
- `<img src="images/x.png">` → `src="{{ url_for('static', filename='images/x.png') }}"`
- `<a href="page.html">` → `href="{{ url_for('route_name') }}"`

### API Integration in `new_analysis_upload.html`
- Analyze button now POSTs to `/api/analyze` instead of navigating
- Results stored in `localStorage` for `results.html` to display

### Everything Else
- All original logic preserved
- Client-side CURB-65 calculator still works
- Drag & drop file upload still works
- 100% backward compatible (just moved files + added backend)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'flask'` | Run `pip install -r requirements.txt` |
| Port 5000 in use | Change port in `app.py` line 180: `port=5001` |
| Images not loading | Check `static/images/` folder has .png files |
| CSS not applied | Check `static/css/style.css` exists |
| Upload fails | Check `uploads/` folder exists |

## What You Get

✅ Full frontend working  
✅ Backend API for image + CURB-65  
✅ File upload handling  
✅ Placeholder AI model (ready for real model)  
✅ Results displayed from API  
✅ Clean code organization  
✅ Ready to add database  
✅ Ready to deploy  

---

**Questions?** Check `README.md` or `SETUP_COMPLETE.md` for more details.


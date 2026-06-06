# Environment Configuration Guide

Complete documentation of all environment variables for PneumoDetect deployment across different platforms.

## Quick Platform Summary

| Platform | Database | Config Method | Timeout |
|----------|----------|---|---------|
| **Local Dev** | XAMPP MySQL | `.env` file | N/A |
| **Azure App Service** | MySQL Flexible Server | Azure Portal | 300s |
| **Heroku/Railway** | MySQL Add-on | Dashboard vars | 120s |
| **Render** | Any MySQL | Dashboard vars | 120s |

---

## Environment Variables Reference

### **Core Flask Configuration**

```env
# Flask Environment Mode
FLASK_ENV=development              # Set to 'production' for deployments
FLASK_DEBUG=True                   # Enable debug mode (development only)

# Secret Key for Session Management
SECRET_KEY=your-secret-key-here    # Change in production! Generate with secrets.token_hex(32)

# Session Configuration
SESSION_COOKIE_HTTPONLY=True       # Prevent JavaScript access to session cookies
SESSION_COOKIE_SECURE=False        # Set to True in production with HTTPS
PERMANENT_SESSION_LIFETIME=86400   # Session timeout in seconds (24 hours)
```

---

### **Database Configuration**

The application auto-detects database format based on available variables:

#### **Option 1: Local Development (XAMPP)**
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=pneumodetect
```

#### **Option 2: Platform-Specific Format (Railway/Render with env vars)**
```env
MYSQLHOST=your-host.mysql.database.azure.com
MYSQLPORT=3306
MYSQLUSER=admin@servername
MYSQLPASSWORD=your-password
MYSQLDATABASE=pneumodetect
```

#### **Option 3: Connection String Format (Render)**
```env
DATABASE_URL=mysql://username:password@host:port/database_name
```

#### **Option 4: Azure MySQL Flexible Server**
```env
MYSQL_HOST=your-server.mysql.database.azure.com
MYSQL_USER=adminuser@your-server
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=pneumodetect
MYSQL_PORT=3306
```

**Priority order (app.py auto-detection):**
1. If `DATABASE_URL` exists → parse full connection string
2. Else if `MYSQLHOST` exists → use platform format
3. Else → use local `MYSQL_HOST` format

---

### **AI Model Configuration**

```env
# Pneumonia Detection Model
PNEUMONIA_MODEL_PATH=models/pneumonia_model.h5

# X-Ray Validator (Image Classification Model)
XRAY_VALIDATOR_MODEL_PATH=models/xray_detector.h5

# X-Ray Validator Strict Mode
XRAY_VALIDATION_STRICT=true        # true = reject non-X-ray images, false = accept all

# Confidence Threshold for X-Ray Validation
XRAY_VALIDATOR_THRESHOLD=0.5       # 0.0-1.0 (50% by default)

# X-Ray Validator Class Label Interpretation
XRAY_POSITIVE_LABEL=xray           # 'xray' or 'non_xray' (determines confidence calculation)

# Model Output Class Index
XRAY_CLASS_INDEX=1                 # Index of positive class in model output (for multi-class)
```

**X-Ray Validator Behavior:**
- When `XRAY_VALIDATION_STRICT=true`: Rejects uploads with `confidence < XRAY_VALIDATOR_THRESHOLD`
- When `XRAY_VALIDATION_STRICT=false`: Logs low confidence but allows upload (non-blocking)
- Model output always logged for debugging if threshold-related issues occur

---

### **File Upload Configuration**

```env
UPLOAD_FOLDER=uploads              # Directory for user uploaded files
MAX_CONTENT_LENGTH=16777216         # Max upload size in bytes (16MB default)

# Allowed File Extensions
ALLOWED_EXTENSIONS=png,jpg,jpeg,bmp,gif
```

---

### **Deployment & Server Configuration**

```env
# Heroku/Railway/Render
PORT=5000                          # Web server port (auto-assigned by platform)

# Gunicorn Worker Configuration
WORKERS=1                          # Number of worker processes (1 for single-threaded)
TIMEOUT=120                        # Request timeout in seconds (increase for Azure to 300)

# Azure App Service Specific
WEBSITES_ENABLE_APP_SERVICE_STORAGE=true
```

**Startup commands by platform:**
```bash
# Local development
python app.py

# Heroku/Railway (use Procfile)
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120

# Azure App Service (use Procfile with longer timeout)
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300

# Render
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```

---

### **Optional: Application Features Toggle**

```env
# Feature Flags (if implemented)
ENABLE_ALERTS=true                 # Enable alert system
ENABLE_PDF_REPORTS=true            # Enable PDF report generation
ENABLE_ANALYTICS=true              # Enable analytics dashboard

# Notification Settings
ALERT_SEVERITY_THRESHOLD=2         # Send alert if CURB-65 >= this value
ALERT_CONFIDENCE_THRESHOLD=70      # Send alert if pneumonia confidence >= this %
```

---

## Platform-Specific Setup

### **Local Development (Windows/Mac/Linux)**

1. **Create `.env` file:**
```bash
copy .env.template .env
```

2. **Edit `.env` with local settings:**
```env
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=dev-secret-key-123
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=pneumodetect
XRAY_VALIDATION_STRICT=true
```

3. **Run application:**
```bash
python app.py
```

---

### **Azure App Service + MySQL Flexible Server**

1. **In Azure Portal, set Application Settings:**
   - `FLASK_ENV` = `production`
   - `FLASK_DEBUG` = `False`
   - `SECRET_KEY` = (generate secure value)
   - `MYSQL_HOST` = `your-server.mysql.database.azure.com`
   - `MYSQL_USER` = `adminuser@your-server`
   - `MYSQL_PASSWORD` = (from Azure MySQL setup)
   - `MYSQL_DATABASE` = `pneumodetect`
   - `SESSION_COOKIE_SECURE` = `True`
   - `XRAY_VALIDATION_STRICT` = `true`

2. **Procfile (Azure uses this):**
```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300
```

3. **Deploy via Git:**
```bash
git remote add azure <your-azure-repo-url>
git push azure main
```

**⚠️ Important for Azure:**
- Use `TIMEOUT=300` (higher than other platforms for slower connections)
- Enable HTTPS-only in Azure App Service settings
- Set `SESSION_COOKIE_SECURE=True` in production

---

### **Heroku**

1. **Install Heroku CLI and login:**
```bash
heroku login
heroku create your-app-name
```

2. **Set environment variables:**
```bash
heroku config:set FLASK_ENV=production
heroku config:set MYSQL_HOST=<your-db-host>
heroku config:set MYSQL_USER=<your-db-user>
heroku config:set MYSQL_PASSWORD=<your-db-password>
heroku config:set MYSQL_DATABASE=pneumodetect
heroku config:set SECRET_KEY=<generate-secure-key>
heroku config:set SESSION_COOKIE_SECURE=True
```

3. **Deploy:**
```bash
git push heroku main
```

---

### **Railway**

1. **Create project and connect GitHub**

2. **Set environment variables (use MYSQLHOST format):**
```env
FLASK_ENV=production
MYSQLHOST=your-railway-host
MYSQLPORT=3306
MYSQLUSER=root
MYSQLPASSWORD=<token>
MYSQLDATABASE=pneumodetect
SECRET_KEY=<secure-key>
```

3. **Deploy from Git push**

---

### **Render**

1. **Create Web Service, connect GitHub**

2. **Set environment variables:**
```env
FLASK_ENV=production
DATABASE_URL=mysql://username:password@host:3306/pneumodetect
SECRET_KEY=<secure-key>
SESSION_COOKIE_SECURE=True
```

3. **Set Build Command:** `pip install -r requirements.txt`

4. **Set Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`

---

## Security Best Practices

```env
# ✅ DO
SECRET_KEY=<generate-with-secrets.token_hex(32)>
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=True          # In production with HTTPS only
FLASK_DEBUG=False                   # In production

# ❌ DON'T
SECRET_KEY=default-key-12345        # Change this!
FLASK_DEBUG=True                    # In production
MYSQL_PASSWORD=password123          # Use strong passwords
```

---

## Troubleshooting

### **Database Connection Issues**
- Check variable names match platform format (MYSQL_HOST vs MYSQLHOST)
- Verify database server is accessible from app server
- Test connection string in MySQL client first

### **X-Ray Validator Rejecting Valid Images**
- Check `XRAY_VALIDATION_STRICT` is set correctly
- Verify `XRAY_VALIDATOR_THRESHOLD` is appropriate (0.3-0.7)
- Ensure `xray_detector.h5` model exists in `models/` folder
- Temporarily set `XRAY_VALIDATION_STRICT=false` to debug

### **Session/Authentication Errors**
- Verify `SECRET_KEY` is set and consistent
- Check `SESSION_COOKIE_HTTPONLY=True` and `SESSION_COOKIE_SECURE` match deployment (HTTPS)
- Clear browser cookies and try again

### **Model Loading Errors**
- Verify model paths exist: `models/pneumonia_model.h5`, `models/xray_detector.h5`
- Check TensorFlow version matches model format
- Ensure sufficient disk space for model files (usually <200MB)

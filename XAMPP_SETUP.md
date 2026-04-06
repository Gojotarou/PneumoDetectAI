# PneumoDetect + XAMPP Setup Guide

## XAMPP Quick Setup

### 1. Start XAMPP

1. Open **XAMPP Control Panel**
2. Click **Start** next to **MySQL**
3. You should see the status change to green ✓

### 2. Create Database

#### Option A: Using phpMyAdmin (Easiest)

1. Open browser → `http://localhost/phpmyadmin/`
2. Click **SQL** tab (top menu)
3. Paste this SQL and click **Go**:

```sql
CREATE DATABASE pneumodetect;
```

Done! Database is created.

#### Option B: Using MySQL Command Line

1. Open **Command Prompt** or **PowerShell**
2. Navigate to XAMPP MySQL bin:
   ```powershell
   cd "C:\xampp\mysql\bin"
   ```

3. Connect to MySQL:
   ```powershell
   mysql -u root
   ```

4. Create database:
   ```sql
   CREATE DATABASE pneumodetect;
   EXIT;
   ```

### 3. Update .env File (Already Done ✓)

Your `.env` file is already configured for XAMPP:
```
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=pneumodetect
```

### 4. Test Installation

Run the Flask app:

```powershell
cd "c:\Users\user\Documents\UNIMAS Education\Sem 7\V"
python app.py
```

You should see:
```
Initializing database...
✓ Database initialized successfully
✓ Pneumonia CNN model loaded successfully
 * Running on http://localhost:5000
```

### 5. Verify in phpMyAdmin

1. Go to `http://localhost/phpmyadmin/`
2. Look in left sidebar for **pneumodetect** database
3. Click it to see the tables: `patients`, `analyses`, `annotations`

## XAMPP vs Standalone MySQL

| Feature | XAMPP | Standalone MySQL |
|---------|-------|------------------|
| Easy to start/stop | ✓ GUI Control Panel | Command line |
| Included in bundle | Apache + PHP + MySQL | MySQL only |
| For beginners | ✓ Best choice | More complex |
| phpMyAdmin | ✓ Included | Need to install |

## Troubleshooting

### MySQL Won't Start in XAMPP
- **Error**: "MySQL already running" or "Port 3306 in use"
- **Solution**: 
  1. Open Task Manager
  2. Search for `mysqld.exe`
  3. End Task
  4. Try starting again in XAMPP

### Can't access phpmyadmin
- Make sure Apache is also running (green ✓)
- Check URL: `http://localhost/phpmyadmin/`

### Connection Error "Access denied"
- XAMPP root user has **no password** by default
- If you set a password, update `.env`:
  ```
  MYSQL_PASSWORD=your_password
  ```

### Port 3306 Already in Use
This happens if MySQL is running multiple times:
```powershell
# Find and kill MySQL process
netstat -ano | findstr :3306
taskkill /PID <PID> /F
```

## Next Steps

✅ Start XAMPP MySQL
✅ Create `pneumodetect` database
✅ Run `python app.py`
✅ Open browser to `http://localhost:5000`
✅ Test by uploading a chest X-ray

All data will be saved to MySQL and persist between sessions!

## Access Your Data

**In phpMyAdmin:**
- View patients: `SELECT * FROM patients;`
- View analyses: `SELECT * FROM analyses;`
- View annotations: `SELECT * FROM annotations;`

**In Python:**
```python
from app import db, Patient, Analysis
with app.app_context():
    patients = Patient.query.all()
    for p in patients:
        print(p.name, p.medical_id)
```

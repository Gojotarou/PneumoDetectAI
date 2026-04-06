# MySQL Setup Guide for PneumoDetect

## Prerequisites
- MySQL Server installed and running
- MySQL user with privileges to create databases

## Setup Steps

### 1. Create MySQL Database

Open MySQL command line or MySQL Workbench and run:

```sql
CREATE DATABASE pneumodetect;
```

### 2. Create MySQL User (Optional but Recommended)

```sql
CREATE USER 'pneumo_user'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON pneumodetect.* TO 'pneumo_user'@'localhost';
FLUSH PRIVILEGES;
```

### 3. Update .env File

Edit the `.env` file in your project root with your MySQL credentials:

```
MYSQL_HOST=localhost
MYSQL_USER=root          # Change to 'pneumo_user' if you created a new user
MYSQL_PASSWORD=your_password_here
MYSQL_DATABASE=pneumodetect
```

### 4. Verify Connection

Try running the Flask app:

```powershell
python app.py
```

You should see:
```
Initializing database...
✓ Database initialized successfully
✓ Pneumonia CNN model loaded successfully
```

## Database Schema

The database will automatically create these tables:

### patients
- id (PRIMARY KEY)
- medical_id (UNIQUE)
- name
- age
- contact
- notes
- created_at
- updated_at

### analyses
- id (PRIMARY KEY)
- patient_id (FOREIGN KEY)
- age, confusion, urea, respiratory_rate, systolic_bp, diastolic_bp
- pneumonia_detected (BOOLEAN)
- confidence (FLOAT)
- curb_score (INT)
- curb_risk (VARCHAR)
- image_filename
- image_base64 (LONGTEXT)
- created_at
- updated_at

### annotations
- id (PRIMARY KEY)
- analysis_id (FOREIGN KEY)
- doctor_name
- final_diagnosis
- clinical_notes (TEXT)
- treatment_plan (TEXT)
- follow_up_instructions (TEXT)
- created_at
- updated_at

## Troubleshooting

### "ModuleNotFoundError: No module named 'mysql.connector'"
Solution: Run `pip install mysql-connector-python==8.0.33`

### "Connection refused"
Solution: Make sure MySQL server is running. On Windows:
```powershell
net start MySQL80
```

### "Access denied for user"
Solution: Check your .env file for correct username and password

### "Unknown database 'pneumodetect'"
Solution: Create the database using the SQL command above

## Next Steps

1. Start the Flask app: `python app.py`
2. Test by uploading an X-ray analysis
3. Check MySQL with: `SELECT * FROM pneumodetect.patients;`
4. Data should now persist across sessions!

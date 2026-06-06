# Default Procfile for Heroku, Railway, Render
# Gunicorn WSGI server with 1 worker process and 120s request timeout
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120

# NOTE: For Azure App Service, increase TIMEOUT to 300s due to potential slower connections
# web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300
#
# Platform-Specific Notes:
# - Heroku: Uses this Procfile automatically
# - Railway: Copy command to deployment settings if needed
# - Render: Set this as Start Command in dashboard (remove 'web:' prefix)
# - Azure: Modify timeout to 300s for healthcare workloads
#
# Single worker (-workers 1) recommended for:
# - TensorFlow model memory constraints
# - MySQL connection limits
# - Development/small deployments
#
# For high-traffic production, increase workers and adjust timeout accordingly

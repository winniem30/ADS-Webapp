# ADS - Deployment Guide

This guide covers deploying the Money Laundering Detection & Risk Intelligence Platform to production.

---

## Prerequisites

- Python 3.10 or higher
- Git
- Heroku CLI (for Heroku deployment) or equivalent for other platforms
- Database backup plan (for SQLite)
- Trained ML models in `models/` directory

---

## Deployment Checklist

### 1. Environment Setup

#### Local Environment Variables
Copy `.env.example` to `.env` and update values:
```bash
cp .env.example .env
```

Update the following in `.env`:
- `SECRET_KEY`: Generate a strong random key (use `python -c 'import secrets; print(secrets.token_hex(32))'`)
- `FLASK_ENV`: Set to `production`
- `FLASK_DEBUG`: Set to `0`
- `SESSION_COOKIE_SECURE`: Set to `True` for HTTPS

### 2. Model Training

Ensure all ML models are trained before deployment:

#### For Dataset 1 (Daily Transactions Dataset):
```bash
python training/train_dataset1.py
```

#### For Dataset 2 (Bank Transaction Dataset):
```bash
python training/train_dataset2.py
```

#### For Simple/Synthetic datasets (optional):
```bash
python training/train_simple.py
python training/train_synthetic_ml.py
```

Verify model files exist in `models/`:
- `dataset1_rf.pkl`, `dataset1_svm.pkl`, `dataset1_xgb.pkl`
- `dataset2_rf.pkl`, `dataset2_svm.pkl`, `dataset2_xgb.pkl`
- Preprocessing artifacts (scalers, encoders, feature columns)

### 3. Directory Structure

Ensure these directories exist (they will be created automatically):
- `uploads/` - For uploaded datasets
- `reports/` - For generated reports
- `charts/` - For generated charts
- `static/css/`, `static/js/`, `static/images/`

### 4. Production Configuration

The app uses `ProductionConfig` from `config.py` when deployed:
- `DEBUG = False`
- `SESSION_COOKIE_SECURE = True` (requires HTTPS)
- Database: SQLite (consider PostgreSQL for production)

### 5. Deployment Platforms

#### Heroku Deployment

1. **Create Heroku App:**
```bash
heroku create your-app-name
```

2. **Set Environment Variables:**
```bash
heroku config:set SECRET_KEY=your-secret-key
heroku config:set FLASK_ENV=production
heroku config:set FLASK_DEBUG=0
```

3. **Add Buildpack:**
```bash
heroku buildpacks:set heroku/python
```

4. **Deploy:**
```bash
git add .
git commit -m "Deployment commit"
git push heroku main
```

5. **Verify Deployment:**
```bash
heroku open
heroku logs --tail
```

#### Render Deployment

1. **Create account at [render.com](https://render.com)**

2. **Connect your GitHub repository**

3. **Create a new Web Service:**
   - Name: `ads-aml-platform`
   - Environment: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --timeout 120 --workers 1`

4. **Add Environment Variables:**
   - `SECRET_KEY`: Your generated secret
   - `FLASK_ENV`: `production`
   - `FLASK_DEBUG`: `0`

5. **Deploy**

#### Railway Deployment

1. **Install Railway CLI:**
```bash
npm install -g @railway/cli
```

2. **Login:**
```bash
railway login
```

3. **Initialize:**
```bash
railway init
```

4. **Deploy:**
```bash
railway up
```

#### Docker Deployment

1. **Create Dockerfile:**
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads reports charts static/css static/js static/images

CMD ["gunicorn", "app:app", "--timeout", "120", "--workers", "1", "--bind", "0.0.0.0:5000"]
```

2. **Build and Run:**
```bash
docker build -t ads-platform .
docker run -p 5000:5000 --env-file .env ads-platform
```

#### Windows Local Testing

Gunicorn doesn't work on Windows. For local Windows testing, use Waitress:

1. **Install Waitress:**
```bash
pip install waitress
```

2. **Run with Waitress:**
```bash
waitress-serve --port=5000 app:app
```

3. **Access the application:**
   - Open browser and navigate to: `http://127.0.0.1:5000`

---

## Post-Deployment Tasks

### 1. Database Setup
The SQLite database will be created automatically on first run. For production, consider:
- Using PostgreSQL for better performance
- Setting up automated backups
- Configuring connection pooling

### 2. Create Admin User
The app creates a default admin user:
- Username: `admin`
- Password: `admin123`

**IMPORTANT:** Change this password immediately after first login in production!

### 3. SSL/HTTPS
Ensure your deployment platform provides SSL:
- Heroku: Automatic SSL
- Render: Automatic SSL
- Railway: Automatic SSL
- Self-hosted: Use Let's Encrypt or similar

### 4. Monitoring
Set up monitoring for:
- Application logs
- Error tracking (Sentry, Rollbar)
- Performance metrics
- Uptime monitoring

### 5. Backup Strategy
Regularly backup:
- SQLite database (`aml_database.db`)
- Uploaded datasets (if important)
- Generated reports

---

## Troubleshooting

### Application Won't Start
- Check logs: `heroku logs --tail` (Heroku) or platform-specific logs
- Verify all dependencies are installed
- Check Python version matches `runtime.txt`
- Ensure all model files exist in `models/`

### SHAP Installation Issues (Windows)
SHAP requires Microsoft Visual C++ Build Tools on Windows. If installation fails:
- Option 1: Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- Option 2: Deploy to Linux-based platform (Heroku, Render, Railway) where SHAP installs easily
- Option 3: Remove SHAP dependency from requirements.txt (model explainability will be disabled)

To use SHAP without Windows build tools, deploy to a cloud platform (recommended).

### Models Not Loading
- Verify model files are in the repository
- Check file permissions
- Ensure preprocessing artifacts exist
- Re-run training scripts if needed

### Database Errors
- Ensure write permissions for database directory
- Check disk space
- Delete `aml_database.db` to recreate if corrupted

### Upload Failures
- Check file size limit (16MB default)
- Verify allowed extensions (csv, xlsx, xls)
- Ensure upload directory has write permissions

### Performance Issues
- Increase worker count in Procfile: `--workers 4`
- Optimize database queries
- Implement caching
- Consider using PostgreSQL instead of SQLite

---

## Security Considerations

1. **Change Default Passwords:** Change admin password immediately
2. **HTTPS Required:** Ensure SSL is enabled
3. **Secret Key:** Use a strong, randomly generated SECRET_KEY
4. **Session Security:** Ensure SESSION_COOKIE_SECURE is True
5. **Input Validation:** All inputs are validated
6. **File Upload:** Restricted to CSV/Excel with size limits
7. **Dependencies:** Keep dependencies updated regularly

---

## Scaling

### Horizontal Scaling
- Use multiple workers: `--workers 4` in Procfile
- Load balancer configuration
- Session storage: Consider Redis for distributed sessions

### Vertical Scaling
- Increase memory (for large datasets)
- Use SSD storage
- Optimize model loading (preload models)

---

## Maintenance

### Regular Tasks
- Monitor logs for errors
- Check disk space (uploads, reports, charts)
- Update dependencies: `pip install --upgrade -r requirements.txt`
- Backup database regularly
- Review and clean old uploads/reports

### Updates
1. Test changes in development
2. Update model versions if needed
3. Deploy to staging first
4. Deploy to production
5. Monitor for issues

---

## Support

For issues or questions:
- Check application logs
- Review DEPLOYMENT.md troubleshooting section
- Check README.md for general documentation

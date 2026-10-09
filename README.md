# Money Laundering Detection & Risk Intelligence Platform

ADS is a Flask/Jinja application with a vanilla JavaScript frontend. Its public home page is the ADS landing page; the authenticated investigation workspace currently uses the IBM Transactions for Anti-Money Laundering HI-Small dataset. The existing IBM import, saved model, and persisted scores remain the real-data foundation.

## Quick start on Windows

1. Run `setup_windows.bat` once.
2. Run `run_local.bat`.
3. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) and choose **Try ADS**.

The local run script explicitly selects development authentication and offers a local analyst session. This option is available only when `AUTH_MODE=development`; production requires Firebase. To configure Firebase sign-in and Render credentials, follow [AUTHENTICATION.md](AUTHENTICATION.md). No Firebase project values or credentials are included in this repository.

The checked-in evaluation artifact and model are used automatically. The large SQLite database is local/ignored and is not downloaded by setup. Set `IBM_AML_DB` to its path if it is stored elsewhere. Check `/health` for service, database, and model readiness.

For a new local installation, activate `.venv\Scripts\Activate.ps1`, set `$env:IBM_AML_SOURCE` to the actual `HI-Small_Trans.csv`, then run `python -m training.ibm_pipeline inspect` and `python -m training.ibm_pipeline ingest` only when the database is missing. Run `python -m training.ibm_pipeline train` only when you intentionally want to retrain. To populate durable scores, first run `python -m training.ibm_pipeline estimate-score`, review time and storage, then run `python -m training.ibm_pipeline score --yes`. The score job is chunked and resumable; it is never run by web startup.

Run tests with `python -m unittest discover -s tests -v`. IBM API docs and Render transfer instructions are in [IBM_AML.md](IBM_AML.md).

---

## 🚀 Features

### Core Capabilities
- **Multi-Model ML Support**: Random Forest, XGBoost, SVM with ensemble capabilities
- **Automatic Dataset Detection**: Automatically identifies uploaded dataset type (Dataset 1 or Dataset 2)
- **Dual Dataset Support**: Supports two Kaggle datasets with dataset-specific preprocessing and models
- **Real-time Risk Analysis**: Per-transaction risk scoring (0-100) with 5-level classification
- **Interactive Spider/Radar Charts**: Dataset-specific axis visualization for suspicious transactions
- **SHAP Model Explainability**: Force plots, waterfall plots, and feature importance analysis
- **Network Analysis**: Interactive transaction network graphs with D3.js
- **Advanced Feature Engineering**: Transaction velocity, frequency, pattern detection
- **Comprehensive Dashboard**: Real-time statistics, charts, and alerts
- **Search & Filtering**: Advanced search across all transaction fields
- **Report Generation**: CSV, Excel, and PDF exports with visualizations
- **Flask Blueprints Architecture**: Modular, scalable code structure

### Supported Datasets

#### Dataset 1: Daily Transactions Dataset (Kaggle - prasad22)
- **Columns**: date, mode, category, subcategory, note, amount, income/expense, currency
- **Spider Chart Axes**: Amount, Mode, Category, Subcategory, Income/Expense, Frequency, Time, Risk Score, Behavior Score, Transaction Pattern (10 axes)
- **Model Files**: dataset1_rf.pkl, dataset1_svm.pkl, dataset1_xgb.pkl
- **Preprocessing**: Label encoding, scaling, missing value imputation

#### Dataset 2: Bank Transaction Dataset for Fraud Detection (Kaggle - valakhorasani)
- **Columns**: transactionid, accountid, transactionamount, transactiondate, previoustransactiondate, transactiontype, location, deviceid, ip address, merchantid, accountbalance, channel, customerage, customeroccupation, transactionduration, loginattempts
- **Spider Chart Axes**: Transaction Amount, Customer Risk, Transaction Type, Device Risk, Merchant Risk, Location Risk, Frequency, Time Risk, Network Risk, Historical Behaviour, Velocity, AML Score (12 axes)
- **Model Files**: dataset2_rf.pkl, dataset2_svm.pkl, dataset2_xgb.pkl
- **Preprocessing**: Label encoding, scaling, missing value imputation, unseen category handling

### Risk Classification
- **Safe** (0-20%): Green - Normal transactions
- **Low Risk** (20-40%): Blue - Minor concerns
- **Medium Risk** (40-60%): Orange - Requires monitoring
- **High Risk** (60-80%): Red - Immediate attention
- **Critical** (80-100%): Dark Red - Urgent investigation

---

## 📋 Tech Stack

### Backend
- **Python 3.8+**
- **Flask** - Web framework with blueprints
- **Pandas** - Data manipulation
- **NumPy** - Numerical computing
- **Scikit-learn** - ML algorithms
- **XGBoost** - Gradient boosting
- **SHAP** - Model explainability
- **Joblib** - Model persistence
- **SQLite** - Database

### Frontend
- **HTML5** - Markup
- **CSS3** - Styling with custom professional design
- **Bootstrap 5** - UI framework
- **JavaScript** - Interactivity
- **Chart.js** - Charts and graphs
- **Plotly** - Interactive visualizations
- **D3.js** - Network graphs
- **ApexCharts** - Advanced charts

---

## 🏗️ Project Structure

```
ADS-Webapp/
├── app.py                      # Main Flask application
├── config.py                   # Configuration settings (dual dataset support)
├── requirements.txt            # Python dependencies
├── database.py                 # SQLite database operations (dual dataset schema)
├── prediction.py               # ML model prediction engine (auto-detection)
├── visualization.py            # Chart generation (dataset-specific spider charts)
├── routes/                     # Flask blueprints (modular architecture)
│   ├── __init__.py            # Blueprint initialization
│   ├── auth.py                # Authentication routes
│   ├── dashboard.py           # Dashboard routes
│   ├── upload.py              # Upload routes (auto-detection)
│   ├── analysis.py            # Analysis routes
│   ├── report.py              # Report generation routes
│   └── admin.py               # Admin panel routes
├── preprocessing/              # Dataset-specific preprocessing pipelines
│   ├── dataset1_preprocessor.py  # Dataset 1 preprocessing
│   └── dataset2_preprocessor.py  # Dataset 2 preprocessing
├── training/                   # Model training scripts
│   ├── train_dataset1.py       # Train Dataset 1 models
│   └── train_dataset2.py       # Train Dataset 2 models
├── utils/                      # Utility modules
│   ├── dataset_detector.py    # Auto-detect dataset type
│   └── shap_explainer.py      # SHAP model explainability
├── models/                     # Trained ML models (dataset-specific)
│   ├── dataset1_rf.pkl        # Dataset 1 Random Forest
│   ├── dataset1_svm.pkl       # Dataset 1 SVM
│   ├── dataset1_xgb.pkl       # Dataset 1 XGBoost
│   ├── dataset2_rf.pkl        # Dataset 2 Random Forest
│   ├── dataset2_svm.pkl       # Dataset 2 SVM
│   ├── dataset2_xgb.pkl       # Dataset 2 XGBoost
│   ├── dataset1_label_encoders.pkl
│   ├── dataset1_scaler.pkl
│   ├── dataset1_feature_columns.pkl
│   ├── dataset2_label_encoders.pkl
│   ├── dataset2_scaler.pkl
│   └── dataset2_feature_columns.pkl
├── templates/                  # HTML templates
│   ├── base.html              # Base template
│   ├── login.html             # Login page
│   ├── register.html          # Registration
│   ├── dashboard.html         # Main dashboard
│   ├── upload.html            # Dataset upload
│   ├── prediction.html        # Prediction results
│   ├── spider.html            # Spider chart analysis
│   ├── analytics.html         # Analytics dashboard
│   ├── settings.html          # Settings page
│   ├── about.html             # About page
│   ├── transactions.html      # Transaction list
│   ├── transaction_detail.html # Transaction details
│   ├── search.html            # Search page
│   ├── network_analysis.html   # Network graph
│   ├── model_comparison.html   # Model comparison
│   ├── reports.html           # Reports
│   ├── admin.html             # Admin panel
│   └── error.html             # Error page
├── static/                     # Static assets
│   ├── css/
│   │   └── style.css          # Main stylesheet (updated for new pages)
│   ├── js/
│   │   └── main.js            # Main JavaScript (updated for new pages)
│   └── images/                # Images and icons
├── uploads/                    # Uploaded datasets
├── reports/                    # Generated reports
└── charts/                     # Generated charts
```

---

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Setup Steps

1. **Clone the repository**
```bash
cd ADS-Webapp
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Train models for both datasets**

   **Train Dataset 1 models:**
   ```bash
   python training/train_dataset1.py
   ```
   This will train Random Forest, SVM, and XGBoost models for Dataset 1 and save them with dataset-specific filenames.

   **Train Dataset 2 models:**
   ```bash
   python training/train_dataset2.py
   ```
   This will train Random Forest, SVM, and XGBoost models for Dataset 2 and save them with dataset-specific filenames.

   **Note:** Place your Kaggle datasets in the project directory before training:
   - Dataset 1: Daily Transactions Dataset (CSV/Excel)
   - Dataset 2: Bank Transaction Dataset for Fraud Detection (CSV/Excel)

4. **Run the application**
```bash
python app.py
```

5. **Access the application**
   - Open browser and navigate to: `http://127.0.0.1:5000`
   - Default admin credentials:
     - Username: `admin`
     - Password: `admin123`

---

## 📊 Dataset Upload & Auto-Detection

The platform automatically detects which Kaggle dataset has been uploaded by analyzing column names with a 60% matching threshold.

### Upload Process
1. Navigate to the Upload page
2. Drag & drop or select your CSV/Excel file
3. The system automatically detects the dataset type
4. Select the ML model (Random Forest, SVM, or XGBoost)
5. Click "Process" to run predictions
6. View results on the dashboard

### Supported File Formats
- CSV (.csv)
- Excel (.xlsx, .xls)
- Maximum file size: 16MB

### Dataset Detection
- **Dataset 1**: Matches columns like date, mode, category, subcategory, amount, income/expense
- **Dataset 2**: Matches columns like transactionid, accountid, transactionamount, transactiontype, location
- **Unsupported**: Displays friendly error message without crashing

---

## 🔑 Key Features Explained

### 1. Dashboard
- Real-time statistics on transactions
- Risk distribution charts
- Recent alerts and uploads
- Model status indicators
- Interactive visualizations

### 2. Dataset Upload
- Drag & drop file upload
- CSV and Excel support
- Data validation and preview
- Progress tracking
- Model selection

### 3. Spider Chart Analysis
- **Dataset-specific axes**: Different axis sets for Dataset 1 (10 axes) and Dataset 2 (12 axes)
- Interactive hover values
- PNG export capability
- Normalized 0-100 scale
- Color-coded risk levels
- Automatic axis selection based on dataset type

### 4. Network Analysis
- Interactive transaction graph
- Node and edge visualization
- Risk-based coloring
- Zoom and pan support
- Suspicious path highlighting

### 5. Model Comparison
- **Dataset-specific comparison**: Compare models within each dataset
- Side-by-side model performance
- Execution time comparison
- Fraud detection rates
- Accuracy metrics
- ROC curves

### 6. SHAP Explainability
- Force plots for individual predictions
- Waterfall plots for feature contributions
- Summary plots for overall feature importance
- Model-agnostic explanations
- Integrated with prediction results page

### 7. Search & Filtering
- Full-text search
- Field-specific search
- Risk level filters
- Amount range filters
- Date range filters

### 8. Reports
- CSV export
- Excel export
- PDF generation
- Chart inclusion
- Summary statistics

---

## 🔒 Security Features

- Session management
- Password hashing (production-ready with bcrypt)
- Input validation
- SQL injection prevention
- XSS protection
- CSRF protection
- Secure file upload
- Role-based access control

---

## 🎨 UI/UX Features

- Professional banking dashboard design
- Dark/Light mode toggle
- Responsive design
- Animated cards and transitions
- Loading animations
- Modern icons (Font Awesome)
- Professional typography
- Smooth transitions
- Mobile-friendly sidebar

---

## 📈 Performance Optimizations

- Model caching
- Batch processing for large datasets
- Database indexing
- Lazy loading
- Pagination
- Efficient queries
- Memory optimization

---

## 🔧 Configuration

Edit `config.py` to customize:

- Database path
- Upload folder
- Model paths
- Risk thresholds
- Session settings
- Logging configuration
- File size limits

---

## 🚦 API Endpoints

### Authentication
- `POST /auth/login` - User login
- `POST /auth/register` - User registration
- `GET /auth/logout` - User logout

### Dashboard
- `GET /dashboard/dashboard` - Main dashboard
- `GET /dashboard/api/dashboard-stats` - Statistics API
- `GET /dashboard/api/alerts` - Alerts API

### Upload
- `GET /upload/upload` - Upload page
- `POST /upload/upload` - File upload
- `POST /upload/upload/preview` - Data preview

### Analysis
- `GET /analysis/transactions` - Transaction list
- `GET /analysis/transaction/<id>` - Transaction details
- `GET /analysis/search` - Search page
- `GET /analysis/network-analysis` - Network graph
- `GET /analysis/model-comparison` - Model comparison

### Reports
- `GET /reports/reports` - Reports page
- `POST /reports/generate` - Generate report
- `GET /reports/download/<filename>` - Download report

### Admin
- `GET /admin/admin` - Admin panel
- `GET /admin/api/system-logs` - System logs
- `GET /admin/api/model-performance` - Model performance

---

## 🐛 Troubleshooting

### Models not loading
- Ensure dataset-specific model files exist in `models/` directory:
  - Dataset 1: dataset1_rf.pkl, dataset1_svm.pkl, dataset1_xgb.pkl
  - Dataset 2: dataset2_rf.pkl, dataset2_svm.pkl, dataset2_xgb.pkl
- Check file permissions
- Verify model compatibility with scikit-learn version
- Run training scripts if models are missing

### Dataset detection fails
- Verify column names match expected patterns
- Check if file is CSV or Excel format
- Ensure file has required columns for at least one dataset
- Check for unsupported dataset error message

### Preprocessing errors
- Ensure preprocessing artifacts exist:
  - dataset1_label_encoders.pkl, dataset1_scaler.pkl, dataset1_feature_columns.pkl
  - dataset2_label_encoders.pkl, dataset2_scaler.pkl, dataset2_feature_columns.pkl
- Run training scripts to generate preprocessing artifacts
- Check for unseen categories in Dataset 2

### Database errors
- Delete `aml_database.db` to recreate
- Check write permissions
- Ensure SQLite is installed
- Verify dataset_type column exists in uploads table

### Upload failures
- Check file size (max 16MB)
- Verify file format (CSV, XLSX, XLS)
- Check disk space
- Ensure dataset detection is working

### Chart not displaying
- Ensure JavaScript is enabled
- Check browser console for errors
- Verify Plotly/Chart.js CDN access
- Check Kaleido is installed for PNG export

### SHAP not working
- Ensure SHAP is installed (pip install shap)
- Check model compatibility with SHAP explainer
- Verify feature names match preprocessing pipeline
- Check for kernel explainer fallback for SVM

---

## 📝 Development

### Adding New Datasets
1. Create preprocessing pipeline in `preprocessing/new_dataset_preprocessor.py`
2. Create training script in `training/train_new_dataset.py`
3. Update `config.py` with new dataset model and preprocessing file names
4. Update `utils/dataset_detector.py` with new dataset column patterns
5. Update `visualization.py` with new dataset spider chart axes
6. Train models using the training script
7. Upload and test with new dataset

### Adding New Models
1. Train your model and save as `.pkl` file with dataset-specific naming
2. Add to `config.py` DATASET1_MODELS or DATASET2_MODELS dictionary
3. Update training script to include new model
4. Update `prediction.py` to load the model
5. Add model option to upload template

### Adding New Features
1. Create route in appropriate blueprint file in `routes/`
2. Create template in `templates/`
3. Add CSS in `static/css/style.css`
4. Add JavaScript in `static/js/main.js`
5. Update navigation in base template if needed

---

## 🤝 Contributing

This is a production-quality AML detection platform. Contributions welcome for:
- Additional ML models
- New visualization types
- Enhanced security features
- Performance improvements
- UI/UX enhancements

---

## 📄 License

This project is part of the ADS (Accurate Detection Services) AML Detection System.

---

## 👥 Team

**Tejaswini Medandrao** - Tech Lead  
Stanley College of Engineering and Technology | Class of 2027

**Cyber Hackathon 2025 Finalist** · Patna, Bihar

---

## 🙏 Acknowledgments

- Scikit-learn for ML algorithms
- XGBoost for gradient boosting
- Plotly for interactive visualizations
- D3.js for network graphs
- Bootstrap for UI framework
- Flask for web framework

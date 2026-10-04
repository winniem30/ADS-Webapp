# Render Environment Variables Setup

## Step 1: Add Environment Variables in Render Dashboard

Go to your Render service at https://dashboard.render.com and navigate to:
- Your "ads-ef6q" service
- Settings tab
- Environment Variables section

Add the following environment variables:

### Required Variables

```
SECRET_KEY=4c44c13267b984d5020e310cd8f353e9b2300ce9fa3127b899283f1b37117af2
FLASK_ENV=production
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=True
```

### Optional Variables (for customization)

```
MAX_CONTENT_LENGTH=16777216
LOG_LEVEL=INFO
```

## Step 2: Save and Redeploy

After adding the environment variables:
1. Click "Save Changes"
2. Render will automatically trigger a new deployment
3. Wait 2-5 minutes for deployment to complete
4. Visit https://ads-ef6q.onrender.com/ to verify

## Step 3: Test the Application

1. Open https://ads-ef6q.onrender.com/
2. Login with default credentials:
   - Username: `admin`
   - Password: `admin123`
3. **IMPORTANT**: Change the admin password immediately after first login

## Step 4: Database Consideration

Currently, the app uses SQLite which resets on each deployment. For production:

### Option A: Keep SQLite (Simpler)
- Uploads and user data will reset on each deployment
- Suitable for testing/demos
- No additional setup needed

### Option B: Use PostgreSQL (Recommended for Production)
- Data persists across deployments
- Better performance
- Requires database migration (I can help with this)

### To Add PostgreSQL on Render:
1. Go to Render dashboard
2. Click "New" → "PostgreSQL"
3. Create a free PostgreSQL database
4. Add the connection URL as `DATABASE_URL` environment variable
5. I'll need to update the code to use SQLAlchemy instead of raw SQLite

Would you like me to proceed with PostgreSQL migration?

# 🔑 Deployment Environment Variables Guide

## ⚠️ CRITICAL: SECRET_KEY Configuration Error

If you're getting this error during deployment:
```
Error: SECRET_KEY is not configured! Please set SECRET_KEY or JWT_SECRET_KEY in your .env file
```

## 🎯 The Problem

Your `.env` file is in `.gitignore` (for security), so it's **NOT being deployed** to your server.

## ✅ Solutions (Choose One)

---

### **Option 1: Set Environment Variables in Your Hosting Platform** (RECOMMENDED)

#### **Heroku**
```bash
heroku config:set SECRET_KEY=smart-token-247bb
heroku config:set JWT_SECRET_KEY=5aa92bffdd6147e9a0c7524d66d32a5ffcd1214e05f3af65aed52de04b90c1da
heroku config:set JWT_ALGORITHM=HS256
heroku config:set ACCESS_TOKEN_EXPIRE_MINUTES=1440
heroku config:set DEBUG=False
heroku config:set ENVIRONMENT=production
```

#### **Railway**
1. Go to your project dashboard
2. Click on your service
3. Go to **Variables** tab
4. Add these variables:
   ```
   SECRET_KEY = smart-token-247bb
   JWT_SECRET_KEY = 5aa92bffdd6147e9a0c7524d66d32a5ffcd1214e05f3af65aed52de04b90c1da
   JWT_ALGORITHM = HS256
   ACCESS_TOKEN_EXPIRE_MINUTES = 1440
   DEBUG = False
   ENVIRONMENT = production
   ```

#### **Render**
1. Go to your service dashboard
2. Click **Environment** tab
3. Add these environment variables:
   ```
   SECRET_KEY = smart-token-247bb
   JWT_SECRET_KEY = 5aa92bffdd6147e9a0c7524d66d32a5ffcd1214e05f3af65aed52de04b90c1da
   JWT_ALGORITHM = HS256
   ACCESS_TOKEN_EXPIRE_MINUTES = 1440
   DEBUG = False
   ENVIRONMENT = production
   ```

#### **AWS Elastic Beanstalk**
1. Go to EB Console → Your Environment → Configuration
2. Click **Software** → **Edit**
3. Add **Environment properties**:
   ```
   SECRET_KEY = smart-token-247bb
   JWT_SECRET_KEY = 5aa92bffdd6147e9a0c7524d66d32a5ffcd1214e05f3af65aed52de04b90c1da
   JWT_ALGORITHM = HS256
   ACCESS_TOKEN_EXPIRE_MINUTES = 1440
   ```

#### **DigitalOcean App Platform**
1. Go to your app → **Components** → **Settings**
2. Scroll to **Environment Variables**
3. Add these variables:
   ```
   SECRET_KEY = smart-token-247bb
   JWT_SECRET_KEY = 5aa92bffdd6147e9a0c7524d66d32a5ffcd1214e05f3af65aed52de04b90c1da
   JWT_ALGORITHM = HS256
   ACCESS_TOKEN_EXPIRE_MINUTES = 1440
   ```

#### **VPS/Dedicated Server (Ubuntu/CentOS)**
Create `.env` file in your project directory:
```bash
cd /path/to/PulseQ_Backend
nano .env
```

Paste your `.env` content, save and exit.

Or set as system environment variables:
```bash
export SECRET_KEY=smart-token-247bb
export JWT_SECRET_KEY=5aa92bffdd6147e9a0c7524d66d32a5ffcd1214e05f3af65aed52de04b90c1da
export JWT_ALGORITHM=HS256
export ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

Add to `~/.bashrc` or `~/.profile` to persist:
```bash
echo 'export SECRET_KEY=smart-token-247bb' >> ~/.bashrc
echo 'export JWT_SECRET_KEY=5aa92bffdd6147e9a0c7524d66d32a5ffcd1214e05f3af65aed52de04b90c1da' >> ~/.bashrc
source ~/.bashrc
```

---

### **Option 2: Upload `.env` File to Server** (Less Secure)

If you must use `.env` file on server:

1. Copy your local `.env` file to the server:
```bash
scp .env user@your-server:/path/to/PulseQ_Backend/.env
```

2. Set proper permissions:
```bash
chmod 600 /path/to/PulseQ_Backend/.env
```

---

## 🔐 Generate a Strong Production SECRET_KEY

**Don't use the default key in production!** Generate a new one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Example output:
```
69674d1667e95759d62d112f9287ced3f656199f0e9857ecbdf7e3e2381f56a9
```

Use this generated key as your `SECRET_KEY`.

---

## 📋 Complete Required Environment Variables

For deployment, you need at minimum:

```env
# Required
SECRET_KEY=your-secret-key-here
# OR
JWT_SECRET_KEY=your-jwt-secret-key-here

# Recommended
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
DEBUG=False
ENVIRONMENT=production
PORT=10000

# Database (if using PostgreSQL)
DB_HOST=your-db-host
DB_NAME=your-db-name
DB_USER=your-db-user
DB_PASSWORD=your-db-password
DB_PORT=5432
```

---

## ✅ Verify Configuration

After setting environment variables, restart your app and check logs for:
```
✅ Configuration Loaded Successfully!
```

If you still see the error, verify the variables are set:

**On Heroku:**
```bash
heroku config:get SECRET_KEY
```

**On VPS/Linux:**
```bash
echo $SECRET_KEY
```

**In Python:**
```python
import os
print(os.getenv('SECRET_KEY'))
```

---

## 🚨 Security Notes

1. **Never commit `.env` to Git** (it's already in `.gitignore`)
2. **Generate a new SECRET_KEY for production** (don't use the default)
3. **Rotate keys regularly** for security
4. **Use platform secrets management** (Heroku Config Vars, AWS Secrets Manager, etc.)

---

## 📞 Still Having Issues?

1. Check deployment logs for error messages
2. Verify environment variables are actually set in your platform
3. Ensure no typos in variable names (case-sensitive!)
4. Restart/redeploy after setting variables
5. Check that `python-dotenv` is in your `requirements.txt`

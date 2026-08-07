# 🚀 Deployment Guide - News Intelligence Dashboard

This guide will help you deploy the News Intelligence Dashboard to the public using Streamlit Cloud.

## Prerequisites

✅ GitHub account (free)  
✅ Streamlit account (free)  
✅ This repository pushed to GitHub  

## Step-by-Step Deployment

### 1️⃣ Prepare Your Repository

Make sure all changes are committed and pushed to GitHub:

```bash
cd /workspaces/Google_News_Scrapping
git add .
git commit -m "Prepare for Streamlit Cloud deployment"
git push origin main
```

**Files that must exist:**
- ✅ `streamlit_app.py` (entry point)
- ✅ `requirements.txt` (dependencies)
- ✅ `.streamlit/config.toml` (Streamlit settings)
- ✅ `README.md` (documentation)

### 2️⃣ Create Streamlit Cloud Account

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "Sign up" or "Sign in with GitHub"
3. Authorize Streamlit to access your GitHub repositories

### 3️⃣ Deploy the App

1. On Streamlit Cloud dashboard, click **"New app"**
2. Select your repository:
   - **Repository**: `yenrosagala/Google_News_Scrapping`
   - **Branch**: `main`
   - **Main file path**: `streamlit_app.py`
3. Click **"Deploy"**
4. Wait for deployment to complete (usually 2-3 minutes)
5. Your app URL will be: `https://yenrosagala-google-news-scrapping-[random].streamlit.app`

### 4️⃣ Access the App

Your app is now **PUBLIC** and accessible at the generated URL!

**Public URL example:**
```
https://yenrosagala-google-news-scrapping-xxxxx.streamlit.app
```

Share this link with anyone to access the dashboard.

---

## Configuration

### Database Selection

The app automatically chooses storage based on configuration:

#### Option A: SQLite (Default - No Configuration Needed)
- Stores data in `berita_google_news.db`
- Perfect for small to medium use
- **No secrets needed**

#### Option B: PostgreSQL (For Production)

If you want to use PostgreSQL in production:

1. Create a PostgreSQL database (e.g., on [render.com](https://render.com) or [supabase.com](https://supabase.com))
2. Get your connection string: `postgresql://user:password@host:port/dbname`
3. In Streamlit Cloud dashboard:
   - Go to **Settings** → **Secrets**
   - Add:
     ```toml
     DATABASE_URL_TEMPLATE = "postgresql://user:password@host:port/dbname"
     ```
   - Click **Save**
4. App will auto-rerun with new database

---

## User Authentication

The app has built-in authentication with two user types:

### 👥 User Umum (Public Access)
- No password required
- Can view all data and analytics
- **Cannot** delete database
- **Use for**: Stakeholders, general viewers

### 🔐 User Login (Admin)
- Requires password authentication
- Can view all data and analytics
- **Can** delete database records
- **Use for**: Administrators, data managers

**To set admin password:**
1. Set `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `app/core/config.py` (or the corresponding secrets/env vars it reads)
2. The check itself lives in `app/core/auth.py` > `render_login_form()`
3. Deploy changes to Streamlit Cloud

---

## Accessing Admin Features

### Password Setting

Admin credentials are read from `Config.ADMIN_USERNAME` / `Config.ADMIN_PASSWORD` in
`app/core/config.py` and checked in `app/core/auth.py`:
```python
if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
    # Allow login
```

### Redeploying After Changes

```bash
git add app/core/config.py
git commit -m "Update admin password"
git push origin main
```

Streamlit Cloud automatically deploys on push to main branch!

---

## Features Available

✨ **Public Features** (Both user types):
- 📊 Real-time dashboard with KPI cards
- 📈 Sentiment analysis charts (pie, bar, line)
- 💾 Data filtering by keyword, sentiment, media, date
- 📝 Executive summary of article content
- 💾 Download data as CSV (semicolon-delimited)
- 📄 View full article content

🔒 **Admin Features** (User Login only):
- 🚀 Run Google News scraping
- 🗑️ Delete all database records
- 🔐 Full access control

---

## Troubleshooting

### App Won't Deploy
**Error:** "Build failed"
- Check `requirements.txt` syntax
- Ensure all dependencies are listed
- View deployment logs in Streamlit Cloud dashboard

### Can't Connect to Database
**Error:** "connection failed"
- If using PostgreSQL, check `DATABASE_URL_TEMPLATE` in secrets
- If using SQLite, should work automatically
- Verify database credentials are correct

### Scraping Returns No Results
- Google News may have rate limits
- Wait 5 minutes and try again
- Check internet connection

### Performance is Slow
- Streamlit Cloud free tier has limited resources
- Consider upgrading to paid plan
- Or use PostgreSQL instead of SQLite

---

## Monitoring & Maintenance

### Check App Status
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Find your app in the list
3. Click to view app health and logs

### View Logs
- Click on your app in Streamlit Cloud dashboard
- Go to **Logs** tab
- See real-time application output

### Auto-Deploy on Push
Every time you push to the `main` branch, Streamlit Cloud automatically redeploys:
```bash
git push origin main  # Auto-triggers deployment
```

---

## Performance Optimization Tips

1. **Database**: Use PostgreSQL for production
2. **Caching**: Executive summaries are cached (@st.cache_data)
3. **Threading**: Parallel article processing enabled
4. **Connection Pooling**: Requests session with pooling

---

## Security Best Practices

🔒 **Do NOT commit:**
- `.streamlit/secrets.toml` (passwords, API keys)
- `.env` files
- Database credentials

✅ **Do:**
- Use Streamlit Cloud secrets management
- Rotate passwords regularly
- Use strong admin passwords
- Monitor access logs

---

## Sharing Your App

### Public Share Link
Share this URL with anyone:
```
https://yenrosagala-google-news-scrapping-xxxxx.streamlit.app
```

### Embed in Website
```html
<iframe 
  src="https://yenrosagala-google-news-scrapping-xxxxx.streamlit.app?embed=true" 
  height="600" 
  width="100%">
</iframe>
```

### Offline Access
Download your data using the "Download Data" button in the Data tab.

---

## Getting Help

- 📖 [Streamlit Documentation](https://docs.streamlit.io)
- 🆘 [Streamlit Community Forum](https://discuss.streamlit.io)
- 🐛 [GitHub Issues](https://github.com/yenrosagala/Google_News_Scrapping/issues)

---

**Your app is now LIVE and PUBLIC!** 🎉

Share the URL and start monitoring news trends!

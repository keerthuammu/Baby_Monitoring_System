# Complete Guide to Deploying on Render (Free Tier)

This guide provides step-by-step instructions for hosting the **PostgreSQL Database**, **FastAPI Backend**, and **React Frontend Dashboard** on [Render.com](https://render.com).

---

## 🚀 Overview of Hosted Architecture

```
                                  Render Cloud Platform
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                 │
  │   1. PostgreSQL Managed Database                                                │
  │      Name: baby-monitor-db                                                      │
  │      Internal URI: postgres://...                                               │
  │                           ^                                                     │
  │                           │ Database Connection                                 │
  │                           v                                                     │
  │   2. Web Service (FastAPI Backend)                                              │
  │      URL: https://baby-monitor-backend.onrender.com                             │
  │      Health Check: /health                                                      │
  │                           ^                                                     │
  │                           │ REST API Polling & Ingestion                        │
  │              ┌────────────┴────────────┐                                        │
  │              │                         │                                        │
  │   3. Static Site (React)     4. IoT ESP32 / Simulator                          │
  │      https://baby-monitor.     HTTP POST to https://...                         │
  │      onrender.com                                                               │
  │                                                                                 │
  └─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Method 1: Automatic 1-Click Blueprint Deployment (Recommended)

Because we added a `render.yaml` blueprint to the root of your repository, Render can deploy the entire stack automatically in one step.

1. **Sign Up / Log In to Render:**
   - Go to [https://render.com](https://render.com).
   - Sign in using your **GitHub account** (`keerthuammu`).

2. **Connect the Blueprint:**
   - In the Render Dashboard, click the **New +** button (top right).
   - Select **Blueprint**.
   - Connect your GitHub repository: `keerthuammu/Baby_Monitoring_System`.
   - Render will detect `render.yaml` and display:
     - 🗄️ **Database:** `baby-monitor-db` (PostgreSQL)
     - ⚙️ **Web Service:** `baby-monitor-backend` (Python)
     - 🖥️ **Static Site:** `baby-monitor-frontend` (React)

3. **Click "Apply":**
   - Click **Apply**.
   - Render will provision the PostgreSQL database, install the Python backend requirements, build the React frontend, and link the environment variables automatically.
   - Wait 3–5 minutes until all 3 services show a green **Live** badge.

---

## Method 2: Manual Step-by-Step Deployment

If you prefer setting up each component individually via the Render UI:

### Step 1: Deploy the PostgreSQL Database
1. In Render, click **New +** ➔ **PostgreSQL**.
2. Fill in the details:
   - **Name:** `baby-monitor-db`
   - **Database:** `baby_monitor_db`
   - **User:** `postgres`
   - **Region:** Choose the region closest to you (e.g., *Singapore* or *Oregon*).
   - **Instance Type:** `Free`.
3. Click **Create Database**.
4. Once created, copy the **Internal Database URL** (e.g., `postgres://postgres:password@dpg-...:5432/baby_monitor_db`).

---

### Step 2: Deploy the FastAPI Backend
1. Click **New +** ➔ **Web Service**.
2. Select your repository: `keerthuammu/Baby_Monitoring_System`.
3. Configure the settings:
   - **Name:** `baby-monitor-backend`
   - **Language:** `Python 3`
   - **Region:** Same region as your database.
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`.
4. Add **Environment Variables** (under *Environment Variables* section):
   | Key | Value |
   | :--- | :--- |
   | `ENVIRONMENT` | `production` |
   | `DATABASE_URL` | *(Paste the Internal Database URL from Step 1)* |
   | `API_KEY` | `baby_monitor_device_secret_key_123` |
   | `SECRET_KEY` | *(Any random 32-character string)* |
   | `CORS_ORIGINS` | `*` |
   | `SOUND_HIGH_THRESHOLD` | `65.0` |
5. Click **Deploy Web Service**.
6. When deployment finishes, copy your live backend URL (e.g., `https://baby-monitor-backend.onrender.com`).
   - Test it by visiting: `https://baby-monitor-backend.onrender.com/health` in your browser. It will return `{"status": "healthy", "database": "connected"}`.

---

### Step 3: Deploy the React Frontend Dashboard
1. Click **New +** ➔ **Static Site**.
2. Select your repository: `keerthuammu/Baby_Monitoring_System`.
3. Configure the settings:
   - **Name:** `baby-monitor-dashboard`
   - **Root Directory:** `frontend`
   - **Build Command:** `npm install && npm run build`
   - **Publish Directory:** `dist`
4. Add **Environment Variable**:
   | Key | Value |
   | :--- | :--- |
   | `VITE_API_URL` | *(Your live backend URL from Step 2, e.g., `https://baby-monitor-backend.onrender.com`)* |
5. Add **Rewrite Rule** (for client-side routing):
   - Under **Redirects/Rewrites**, click **Add Rule**:
     - **Source:** `/*`
     - **Destination:** `/index.html`
     - **Action:** `Rewrite`
6. Click **Create Static Site**.
7. When finished, open the frontend URL (e.g., `https://baby-monitor-dashboard.onrender.com`) to see your live dashboard.

---

## 📡 Connecting the ESP32 (or Simulator) to Render

### 1. Update the ESP32 Firmware:
Open `esp32_firmware/smart_baby_monitor/smart_baby_monitor.ino` and update line 43 with your Render backend URL:
```cpp
// Change from local IP to your live Render HTTPS URL:
const char* BACKEND_URL = "https://baby-monitor-backend.onrender.com/api/readings";
```
Upload the sketch to the ESP32. The ESP32 will now transmit telemetry directly to your cloud-hosted database over the internet!

### 2. Update the Python Simulator:
To test your cloud deployment without physical hardware, run:
```powershell
# In PowerShell:
$env:BACKEND_URL="https://baby-monitor-backend.onrender.com/api/readings"
.\backend\.venv\Scripts\python.exe backend/simulate_esp32.py 30
```

---

## 💡 Important Render Free Tier Tips

1. **Free Tier Inactivity Sleep:**
   - Render Web Services on the free plan spin down after 15 minutes of inactivity.
   - When a new request arrives, it takes ~30–50 seconds to "wake up".
   - *College Presentation Tip:* 5 minutes before your demo, open `https://your-backend.onrender.com/health` in your browser to make sure the server is awake and warm!
2. **PostgreSQL Free Tier:**
   - Render's free PostgreSQL database is active for 90 days, which is more than enough for college semester demonstrations and viva evaluation.

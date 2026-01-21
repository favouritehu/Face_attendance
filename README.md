# SmartFaceSystem - One-Click Coolify Deployment

This repository is optimized for deployment on **Coolify** using Docker. It includes a pre-configured `Dockerfile` with all necessary system dependencies for Face Recognition (dlib) and OpenCV.

## 🚀 Deployment Instructions

### 1. Create Service in Coolify
1. Go to your Coolify Dashboard.
2. Click **+ New Resource**.
3. Select **Public Repository** (or Private if you keep this private).
4. Enter your GitHub repository URL.
5. **Build Pack**: Keep as `Dockerfile`.

### 2. Configuration (Essential)
Before hitting "Deploy", go to the **Configuration** tab of your new service:

#### General
- **Port:** `8501`
- **Domains:** Set your domain (e.g., `https://face-system.yourdomain.com`).
  > **⚠️ HTTPS IS MANDATORY:** WebRTC (Camera access) *will not work* without a valid HTTPS connection.

#### Storage (Persistence)
You **MUST** configure these volumes to ensure user data and logs survive redeployments.

| Volume Name / Host Path | Container Path       | Description              |
|-------------------------|----------------------|--------------------------|
| `known_faces`           | `/app/known_faces`   | Stores registered faces  |
| `factory_logs`          | `/app/factory_logs.csv` | Stores attendance logs |

1. Go to **Storage**.
2. Click **Add Storage**.
3. Add `/app/known_faces`.
4. Add `/app/factory_logs.csv`. Note: For a single file, it's often safer to mount the *directory* or rely on the app to recreate the file if the mount is a directory. **Recommendation:** Since Coolify volumes differ, if you can only mount directories, you may need to adjust to mount a data folder. However, for file bind mounts:
   - If using **local path** (bind mount): `path/to/host/logs.csv` -> `/app/factory_logs.csv`
   - If using **Docker volumes**: Just mount a `data` volume to `/app` (be careful not to overwrite code) or mount specific folders.
   - **EASIEST**: Mount a volume to `/app/known_faces` and another to `/app/logs` (if you change code to save logs there).
   - **CURRENT CONFIG**: The app saves to root. 
     - **Option A (Simpler):** Add a volume for `/app/known_faces`. Logs might be ephemeral if not mounted carefully.
     - **Option B (Robust):** Mount `/app/known_faces`. For logs, accept they might be reset or try to mount the file if Coolify supports it.

### 3. Deploy
Click **Deploy**. The build process might take a few minutes as it compiles `dlib`.

## 🛠 Project Structure
- `Dockerfile`: Python 3.10 + build-essential + cmake + app.
- `requirements.txt`: Python deps (headless opencv).
- `main.py`: Core application.
- `known_faces/`: directory for face images.

## 📝 Troubleshooting
- **Build Failures:** Ensure the Dockerfile includes `cmake` and `build-essential` (already included).
- **Camera Not Working:** Ensure you are accessing via `https://` config in Coolify.
- **"Connecting..." indefinitely:** Ensure the port `8501` is exposed and mapped correctly.

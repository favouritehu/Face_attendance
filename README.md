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
| `logs`                  | `/app/logs`          | Stores attendance logs   |

1. Go to **Storage**.
2. Click **Add Storage**.
3. Add VOLUME for `/app/known_faces`.
4. Add VOLUME for `/app/logs`. 

**Why directory mounts?**
Mounting directories (e.g., `/app/logs`) is safer than single files in Docker/Coolify. The app will automatically create `factory_logs.csv` inside the `logs` folder.

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

### ❓ Connection Issues? (STUN/TURN)
If the camera says **"Connection is taking longer than expected..."**, your network (or the server's network) is blocking the P2P connection.

**Solution: Add a TURN Server (Easiest Way - Metered.ca)**

1.  **Get your API URL**: You already have it! It looks like:
    `https://camerafavouritefab.metered.live/api/v1/turn/credentials?apiKey=YOUR_API_KEY`
2.  **In Coolify -> Service -> Environment Variables**, add one simple variable:
    *   `ICE_SERVERS_URL`: `https://camerafavouritefab.metered.live/api/v1/turn/credentials?apiKey=f43166290d8713f4fce8b3ad0dc68e8de0e2`
    *(Replace with your full URL if different)*.
3.  **Redeploy**.

The app will now automatically fetch the fresh TURN credentials from that URL every time it starts. This is much more reliable than hardcoding passwords.

**Why is this needed?**
WebRTC tries to connect Peer-to-Peer. Corporate firewalls, Cloudflare Tunnels, and Docker containers often block this. A TURN server relays the traffic around the blockage.

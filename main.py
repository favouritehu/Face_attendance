import streamlit as st
import cv2
import face_recognition
import numpy as np
import pandas as pd
import os
import shutil
import time
import av
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# --- 1. SYSTEM CONFIGURATION ---
st.set_page_config(page_title="FactoryGuard AI", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")

# --- CONSTANTS & SETTINGS ---
FACES_DIR = 'known_faces'
ATTENDANCE_FILE = 'factory_logs.csv'
REQUIRED_SAMPLES = 10   # Number of photos needed to register
MIN_SHIFT_MINUTES = 60  # How long a shift lasts before they can check out (prevents mistakes)
RESCAN_COOLDOWN = 2     # How many minutes to wait before scanning the same person again

# --- DIRECTORY SETUP ---
os.makedirs(FACES_DIR, exist_ok=True)
if not os.path.exists(ATTENDANCE_FILE):
    pd.DataFrame(columns=['Name', 'Time', 'Date', 'Type']).to_csv(ATTENDANCE_FILE, index=False)

# --- 2. CSS STYLING (Professional Light Theme) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #f8fafc; }
    
    /* Hide Standard Streamlit Elements */
    [data-testid="stSidebar"] { display: none; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    
    /* Navigation Bar */
    .nav-bar {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 15px;
        background: white;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
    
    /* Video Card */
    .video-card {
        background: black;
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        border: 4px solid #334155;
    }
    
    /* Buttons */
    .stButton button {
        height: 3rem;
        font-weight: 700;
        border-radius: 8px;
        text-transform: uppercase;
        width: 100%;
        transition: all 0.2s;
    }
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    /* Metrics */
    div[data-testid="stMetricValue"] { font-size: 1.5rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. CORE LOGIC FUNCTIONS ---

def crop_to_square(image):
    """Crops the center square of an image (removes background walls)."""
    h, w = image.shape[:2]
    min_dim = min(h, w)
    top = (h - min_dim) // 2
    left = (w - min_dim) // 2
    return image[top:top+min_dim, left:left+min_dim]

@st.cache_resource
def load_database():
    """Loads facial data from disk into memory."""
    encs, names = [], []
    for root, _, files in os.walk(FACES_DIR):
        for file in files:
            if file.endswith(('.jpg', '.png')):
                try:
                    path = os.path.join(root, file)
                    img = face_recognition.load_image_file(path)
                    e = face_recognition.face_encodings(img)
                    if e:
                        encs.append(e[0])
                        names.append(os.path.basename(os.path.dirname(path)))
                except: pass
    return encs, names

def delete_user(name):
    """Permanently removes a user and their data."""
    path = os.path.join(FACES_DIR, name)
    if os.path.exists(path):
        shutil.rmtree(path)
        st.cache_resource.clear()
        return True
    return False

def smart_log_logic(name):
    """
    Handles Attendance Logic:
    1. Check-In (Green)
    2. Cooldown (Ignore if scanned recently)
    3. Shift Lock (Prevent accidental checkout for 1 hr - Green)
    4. Check-Out (Red)
    """
    now = datetime.now()
    d_str, t_str = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
    
    try:
        df = pd.read_csv(ATTENDANCE_FILE)
        logs = df[(df['Name'] == name) & (df['Date'] == d_str)]
        
        # 1. FIRST SCAN -> CHECK IN
        if logs.empty:
            pd.DataFrame([[name, t_str, d_str, "CHECK-IN"]], columns=df.columns).to_csv(ATTENDANCE_FILE, mode='a', header=False, index=False)
            return "CHECKED IN", (0, 200, 0) # Green

        last = logs.iloc[-1]
        last_dt = datetime.strptime(f"{last['Date']} {last['Time']}", "%Y-%m-%d %H:%M:%S")
        mins_passed = (now - last_dt).total_seconds() / 60
        
        # 2. ANTIBOUNCE (Ignore spam)
        if mins_passed < RESCAN_COOLDOWN:
            return None, None # Don't update UI

        # 3. SAFETY LOCK (Keep Green if Shift is active)
        if last['Type'] == "CHECK-IN" and mins_passed < MIN_SHIFT_MINUTES:
            mins_left = int(MIN_SHIFT_MINUTES - mins_passed)
            # You requested GREEN for shift status
            return f"ON SHIFT ({mins_left}m)", (0, 200, 0) # Green

        # 4. TOGGLE (Check Out)
        new_type = "CHECK-OUT" if last['Type'] == "CHECK-IN" else "CHECK-IN"
        color = (0, 0, 255) if new_type == "CHECK-OUT" else (0, 200, 0) # Red or Green
        
        pd.DataFrame([[name, t_str, d_str, new_type]], columns=df.columns).to_csv(ATTENDANCE_FILE, mode='a', header=False, index=False)
        return new_type, color
    except:
        return "ERROR", (100, 100, 100)

# --- 4. VIDEO PROCESSING ENGINE ---
class FactoryEngine(VideoProcessorBase):
    def __init__(self):
        self.encodings, self.names = load_database()
        self.frame_skip = 0
        self.last_results = []

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        self.frame_skip += 1
        
        # Optimize: Run AI every 2nd frame
        if self.frame_skip % 2 == 0:
            # Resize to 0.5x (720p -> 360p) for speed
            small = cv2.resize(img, (0, 0), fx=0.5, fy=0.5)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            
            # Upsample 2x to see faces from far away
            locs = face_recognition.face_locations(rgb, number_of_times_to_upsample=2)
            encs = face_recognition.face_encodings(rgb, locs)
            
            new_results = []
            for enc, loc in zip(encs, locs):
                matches = face_recognition.compare_faces(self.encodings, enc, tolerance=0.42)
                name = "Unknown"
                color = (200, 200, 200) # Grey default
                status = ""
                
                if True in matches:
                    idx = matches.index(True)
                    name = self.names[idx]
                    res = smart_log_logic(name)
                    if res and res[0]:
                        status, rgb_color = res
                        # Convert RGB tuple to BGR for OpenCV
                        color = (rgb_color[2], rgb_color[1], rgb_color[0])
                    else:
                        # Cooldown active, show logged status
                        status = "LOGGED"
                        color = (0, 200, 0)

                new_results.append((name, color, loc, status))
            self.last_results = new_results

        # Draw HUD
        for name, color, loc, status in self.last_results:
            top, right, bottom, left = [v * 2 for v in loc]
            
            # 1. Clean Corner Brackets (Not covering face)
            l = 30
            t = 4
            cv2.line(img, (left, top), (left+l, top), color, t)
            cv2.line(img, (left, top), (left, top+l), color, t)
            cv2.line(img, (right, top), (right-l, top), color, t)
            cv2.line(img, (right, top), (right, top+l), color, t)
            
            cv2.line(img, (left, bottom), (left+l, bottom), color, t)
            cv2.line(img, (left, bottom), (left, bottom-l), color, t)
            cv2.line(img, (right, bottom), (right-l, bottom), color, t)
            cv2.line(img, (right, bottom), (right, bottom-l), color, t)
            
            # 2. Text Label BELOW the face (Unobtrusive)
            # Create a nice background pill
            cv2.rectangle(img, (left, bottom + 15), (right, bottom + 50), color, -1)
            
            # Centered Name
            font_scale = 0.7
            text_size = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)[0]
            text_x = left + (right - left - text_size[0]) // 2
            cv2.putText(img, name, (text_x, bottom + 40), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 2)
            
            # 3. Status Tag (Floating Above)
            if status:
                cv2.rectangle(img, (left, top - 35), (right, top - 5), (0,0,0), -1)
                cv2.putText(img, status, (left + 5, top - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- 5. APP NAVIGATION ---

# Top Navigation Bar
c1, c2, c3, c4 = st.columns(4)
with c1: nav_live = st.button("📡 MONITOR", use_container_width=True)
with c2: nav_reg = st.button("➕ REGISTER", use_container_width=True)
with c3: nav_users = st.button("👥 USERS", use_container_width=True)
with c4: nav_log = st.button("📊 LOGS", use_container_width=True)

# State Management
if 'page' not in st.session_state: st.session_state.page = "Monitor"
if nav_live: st.session_state.page = "Monitor"
if nav_reg: st.session_state.page = "Register"
if nav_users: st.session_state.page = "Users"
if nav_log: st.session_state.page = "Logs"

# --- PAGE 1: LIVE MONITOR ---
if st.session_state.page == "Monitor":
    st.markdown("<h2 style='text-align: center;'>Factory Access Point</h2>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([0.1, 0.8]) # Center the video
    with col2:
        st.markdown('<div class="video-card">', unsafe_allow_html=True)
        # ROBUST CONNECTION SETTINGS (Fixes connection delay)
        rtc_config = RTCConfiguration({
            "iceServers": [
                {"urls": ["stun:stun.l.google.com:19302"]},
                {"urls": ["stun:global.stun.twilio.com:3478"]}
            ]
        })
        
        webrtc_streamer(
            key="factory_monitor",
            video_processor_factory=FactoryEngine,
            rtc_configuration=rtc_config,
            media_stream_constraints={"video": {"width": 1280, "height": 720}, "audio": False},
            async_processing=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

# --- PAGE 2: REGISTRATION ---
elif st.session_state.page == "Register":
    st.markdown("<h2 style='text-align: center;'>New Worker Onboarding</h2>", unsafe_allow_html=True)
    
    if 'reg_buffer' not in st.session_state: st.session_state.reg_buffer = []
    
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"Capture {REQUIRED_SAMPLES} Photos. Center face in frame.")
        img = st.camera_input("Scanner")
        
        if img:
            # Decode BGR
            bytes_data = img.getvalue()
            img_bgr = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
            # Crop Square
            img_square = crop_to_square(img_bgr)
            
            if len(st.session_state.reg_buffer) < REQUIRED_SAMPLES:
                st.session_state.reg_buffer.append(img_square)
                st.toast(f"Photo {len(st.session_state.reg_buffer)} Saved")
    
    with c2:
        name = st.text_input("Worker Name")
        st.progress(len(st.session_state.reg_buffer)/REQUIRED_SAMPLES)
        
        # Preview (Convert to RGB for display)
        if st.session_state.reg_buffer:
            st.image(cv2.cvtColor(st.session_state.reg_buffer[-1], cv2.COLOR_BGR2RGB), width=150)
            
        if st.button("SAVE USER", disabled=len(st.session_state.reg_buffer) < REQUIRED_SAMPLES):
            if name:
                path = os.path.join(FACES_DIR, name)
                os.makedirs(path, exist_ok=True)
                for i, im in enumerate(st.session_state.reg_buffer):
                    # SAVE AS BGR (Important!)
                    cv2.imwrite(os.path.join(path, f"{name}_{i}.jpg"), im)
                st.cache_resource.clear()
                st.session_state.reg_buffer = []
                st.success("User Added Successfully")

# --- PAGE 3: USER MANAGEMENT (Restored!) ---
elif st.session_state.page == "Users":
    st.markdown("<h2 style='text-align: center;'>Employee Database</h2>", unsafe_allow_html=True)
    
    if os.path.exists(FACES_DIR):
        users = sorted([d for d in os.listdir(FACES_DIR) if os.path.isdir(os.path.join(FACES_DIR, d))])
        
        if users:
            sel_user = st.selectbox("Select Employee", users)
            
            c1, c2 = st.columns([1, 2])
            with c1:
                path = os.path.join(FACES_DIR, sel_user)
                imgs = [f for f in os.listdir(path) if f.endswith('.jpg')]
                if imgs:
                    # Load BGR, Convert to RGB for display
                    img_bgr = cv2.imread(os.path.join(path, imgs[0]))
                    st.image(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB), caption="ID Photo")
            
            with c2:
                st.write(f"### {sel_user}")
                st.write(f"Training Samples: {len(imgs)}")
                st.write("Status: **Active**")
                
                if st.button("DELETE USER", type="primary"):
                    delete_user(sel_user)
                    st.success(f"Deleted {sel_user}")
                    time.sleep(1)
                    st.rerun()
        else:
            st.info("No users registered.")

# --- PAGE 4: LOGS ---
elif st.session_state.page == "Logs":
    st.markdown("<h2 style='text-align: center;'>Access Logs</h2>", unsafe_allow_html=True)
    if os.path.exists(ATTENDANCE_FILE):
        df = pd.read_csv(ATTENDANCE_FILE)
        st.dataframe(df.sort_index(ascending=False), use_container_width=True)
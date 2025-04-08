import cv2
import pyautogui
import mediapipe as mp
import tkinter as tk
from tkinter import ttk, messagebox
import platform
import sys
import time
from collections import deque
import numpy as np
import os

# Suppress warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'

def get_camera_names():
    """Get a list of available cameras with verification"""
    camera_list = []
    system = platform.system()
    
    try:
        if system == "Windows":
            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:")
            devices = wmi.InstancesOf("Win32_PnPEntity")
            for device in devices:
                if device.Name and any(key in device.Name for key in ["Camera", "Webcam", "Capture", "Integrated"]):
                    # Verifikasi kamera bisa dibuka
                    cap = cv2.VideoCapture(len(camera_list), cv2.CAP_DSHOW)
                    if cap.isOpened():
                        camera_list.append({
                            'index': len(camera_list),
                            'name': device.Name
                        })
                        cap.release()
                    
        elif system == "Linux":
            import subprocess
            result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            current_cam = {}
            for line in lines:
                if line.strip().startswith('/dev/video'):
                    index = int(line.strip()[-1])
                    cap = cv2.VideoCapture(index)
                    if cap.isOpened():
                        current_cam['index'] = index
                        camera_list.append(current_cam.copy())
                        cap.release()
                elif line.strip() and not line.startswith('\t'):
                    current_cam['name'] = line.strip()
                    
        elif system == "Darwin":
            import subprocess
            result = subprocess.run(['system_profiler', 'SPCameraDataType'], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Camera' in line and 'Connected' in line:
                    name = line.split(':')[0].strip()
                    cap = cv2.VideoCapture(len(camera_list))
                    if cap.isOpened():
                        camera_list.append({
                            'index': len(camera_list),
                            'name': name
                        })
                        cap.release()
    
    except Exception as e:
        pass
    
    # Fallback universal
    for i in range(10):
        try:
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and not any(cam['index'] == i for cam in camera_list):
                camera_list.append({
                    'index': i,
                    'name': f"Camera {i}"
                })
            cap.release()
        except:
            continue
    
    return camera_list

class CameraControlApp:
    def __init__(self):
        self.cameras = get_camera_names()
        
        if not self.cameras:
            messagebox.showerror("Error", "No cameras detected!")
            return
            
        self.root = tk.Tk()
        self.root.title("Select Camera")
        self.setup_gui()
        self.root.mainloop()
        
    def setup_gui(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(expand=True)
        
        ttk.Label(main_frame, 
                 text="Select the Camera to Use:",
                 font=('Arial', 12)).pack(pady=10)
        
        self.cam_var = tk.StringVar()
        self.cam_combobox = ttk.Combobox(
            main_frame,
            textvariable=self.cam_var,
            values=[f"{cam['name']} (Index {cam['index']})" for cam in self.cameras],
            state="readonly",
            width=60
        )
        self.cam_combobox.pack(pady=10)
        self.cam_combobox.current(0)
        
        ttk.Button(
            main_frame,
            text="Start Game Controller",
            command=self.start_controller
        ).pack(pady=15)
        
    def start_controller(self):
        selected_index = self.cam_combobox.current()
        if 0 <= selected_index < len(self.cameras):
            self.root.destroy()
            GDController(self.cameras[selected_index]['index']).start()
        else:
            messagebox.showerror("Error", "Invalid camera selection!")

class GDController:
    def __init__(self, camera_index):
        self.camera_index = camera_index
        self.running = False
        
        # Inisialisasi MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
            model_complexity=0
        )
        
        # Sistem kontrol game
        self.jump_buffer = deque(maxlen=5)
        self.last_jump_time = 0
        self.jump_cooldown = 0.15
        
        # Setup kamera
        self.cap = cv2.VideoCapture(self.camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Failed to open camera!")
            sys.exit()

    def calculate_distance(self, landmarks):
        """Calculating the normalized thumb-index distance"""
        index = landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]
        thumb = landmarks.landmark[self.mp_hands.HandLandmark.THUMB_TIP]
        wrist = landmarks.landmark[self.mp_hands.HandLandmark.WRIST]
        
        # Hitung ukuran tangan
        hand_size = np.linalg.norm([wrist.x - index.x, wrist.y - index.y])
        distance = np.linalg.norm([index.x - thumb.x, index.y - thumb.y])
        
        return distance / (hand_size + 1e-7)

    def process_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        
        if results.multi_hand_landmarks:
            for landmarks in results.multi_hand_landmarks:
                # Gambar landmark
                mp.solutions.drawing_utils.draw_landmarks(
                    frame,
                    landmarks,
                    self.mp_hands.HAND_CONNECTIONS,
                    mp.solutions.drawing_styles.get_default_hand_landmarks_style(),
                    mp.solutions.drawing_styles.get_default_hand_connections_style()
                )
                
                # Deteksi gestur
                norm_distance = self.calculate_distance(landmarks)
                self.jump_buffer.append(norm_distance < 0.35)
        
        return frame

    def update_game(self):
        current_time = time.time()
        if sum(self.jump_buffer) >= 3 and (current_time - self.last_jump_time) > self.jump_cooldown:
            pyautogui.press('space')
            self.last_jump_time = current_time
            self.jump_buffer.clear()

    def draw_ui(self, frame):
        # Status lompat
        cv2.putText(frame, f"JUMP: {sum(self.jump_buffer)}/5", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Cooldown
        cooldown = max(0, self.jump_cooldown - (time.time() - self.last_jump_time))
        cv2.putText(frame, f"CD: {cooldown:.2f}s", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    def start(self):
        self.running = True
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                frame = self.process_frame(frame)
                self.update_game()
                self.draw_ui(frame)
                
                cv2.imshow('GD Controller - Click Q for  quite', frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
            else:
                time.sleep(0.01)
        
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Redirect error output
    sys.stderr = open(os.devnull, 'w')
    
    if platform.system() == "Windows":
        try:
            import win32com.client
        except ImportError:
            messagebox.showerror("Error", 
                "For Windows, install:\npip install pywin32")
            sys.exit()
    
    CameraControlApp()
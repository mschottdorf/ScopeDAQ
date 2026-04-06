import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class DAQImageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scanning Image DAQ - 128x128")
        self.root.geometry("1100x750")
        self.root.minsize(850, 650)
        
        self.is_fullscreen = False
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        
        # State & Data storage
        self.raw_x, self.raw_y, self.raw_z = None, None, None
        self.serial_conn = None
        self.is_live = False
        
        # Core Image Array
        self.PIXELS = 128
        self.TOTAL_BYTES = self.PIXELS * self.PIXELS * 3 
        self.current_img = np.zeros((self.PIXELS, self.PIXELS))
        self.im_obj = None # Matplotlib image object for fast updates
        
        self.setup_ui()

    def setup_ui(self):
        self.main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ctrl_frame = ttk.Frame(self.main_pane, padding=10)
        self.main_pane.add(ctrl_frame, weight=0) 
        
        ttk.Label(ctrl_frame, text="COM Port:").pack(pady=5)
        self.port_entry = ttk.Entry(ctrl_frame)
        self.port_entry.pack(fill='x', pady=5)
        self.port_entry.insert(0, "/dev/ttyACM0")
        
        ttk.Button(ctrl_frame, text="Connect", command=self.connect_serial).pack(fill='x', pady=10)
        ttk.Separator(ctrl_frame, orient='horizontal').pack(fill='x', pady=5)
        
        # --- Demo Controls ---
        demo_frame = ttk.LabelFrame(ctrl_frame, text="Demo Controls")
        demo_frame.pack(fill='x', pady=5)
        ttk.Button(demo_frame, text="Scan X", command=lambda: self.send_command(b'X')).pack(fill='x', pady=2, padx=5)
        ttk.Button(demo_frame, text="Scan Y", command=lambda: self.send_command(b'Y')).pack(fill='x', pady=2, padx=5)
        ttk.Button(demo_frame, text="Scan X + Y", command=lambda: self.send_command(b'B')).pack(fill='x', pady=2, padx=5)
        ttk.Button(demo_frame, text="Stop Motion", command=lambda: self.send_command(b'H')).pack(fill='x', pady=2, padx=5)

        ttk.Separator(ctrl_frame, orient='horizontal').pack(fill='x', pady=10)
        
        # --- Data Acquisition ---
        daq_frame = ttk.LabelFrame(ctrl_frame, text="Data Acquisition")
        daq_frame.pack(fill='x', pady=5)
        
        self.live_btn = ttk.Button(daq_frame, text="▶ Start Live View", command=self.toggle_live)
        self.live_btn.pack(fill='x', pady=2, padx=5)
        
        ttk.Separator(daq_frame, orient='horizontal').pack(fill='x', pady=5, padx=10)
        
        ttk.Button(daq_frame, text="1. Collect Full Frame", command=self.collect_data).pack(fill='x', pady=2, padx=5)
        ttk.Button(daq_frame, text="2. Transfer Frame", command=self.transfer_data).pack(fill='x', pady=2, padx=5)
        ttk.Button(daq_frame, text="3. Save Raw Data", command=self.save_raw_data).pack(fill='x', pady=2, padx=5)
        
        ttk.Separator(ctrl_frame, orient='horizontal').pack(fill='x', pady=10)
        
        # --- Image Adjustments & Zoom ---
        adj_frame = ttk.LabelFrame(ctrl_frame, text="Image & FOV Adjustments")
        adj_frame.pack(fill='x', pady=5)
        
        self.zoom = tk.IntVar(value=100)
        self.contrast = tk.DoubleVar(value=1.0)
        self.brightness = tk.DoubleVar(value=0.0)
        
        self.create_slider(adj_frame, "Zoom (%):", self.zoom, 1, 100, command=self.update_zoom)
        ttk.Separator(adj_frame, orient='horizontal').pack(fill='x', pady=10, padx=5)
        self.create_slider(adj_frame, "Contrast:", self.contrast, 0.1, 5.0, resolution=0.1, command=self.update_image_plot)
        self.create_slider(adj_frame, "Brightness:", self.brightness, -128, 128, command=self.update_image_plot)
        
        ttk.Label(ctrl_frame, text="Press F11 for Fullscreen", font=("Arial", 8, "italic"), foreground="gray").pack(side=tk.BOTTOM, pady=10)

        # --- Image Display ---
        img_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(img_frame, weight=1) 
        
        self.fig, self.ax = plt.subplots(figsize=(6, 6), layout='constrained')
        self.ax.set_title("128x128 Reconstructed Image")
        self.ax.axis('off')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=img_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.update_image_plot() # Initialize blank plot

    def create_slider(self, parent, label_text, variable, vmin, vmax, resolution=1, command=None):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=2, padx=5)
        ttk.Label(frame, text=label_text, width=12).pack(side=tk.LEFT)
        scale = tk.Scale(frame, variable=variable, from_=vmin, to=vmax, 
                         resolution=resolution, orient=tk.HORIZONTAL, 
                         command=lambda e: command() if command else None)
        scale.pack(side=tk.RIGHT, fill='x', expand=True)

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)
        return "break"

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)
        return "break"

    def connect_serial(self):
        port = self.port_entry.get()
        try:
            self.serial_conn = serial.Serial(port, baudrate=115200, timeout=5)
            self.serial_conn.reset_input_buffer()
            # Send initial zoom parameter
            self.update_zoom()
            messagebox.showinfo("Success", f"Connected to {port}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect: {e}")

    def send_command(self, cmd):
        if not self.serial_conn:
            messagebox.showwarning("Warning", "Not connected.")
            return
        self.serial_conn.write(cmd)
        
    def update_zoom(self):
        """Sends the Z byte followed by the zoom value byte."""
        if self.serial_conn:
            val = int(self.zoom.get())
            self.serial_conn.write(b'Z' + bytes([val]))

    def toggle_live(self):
        if not self.serial_conn:
            messagebox.showwarning("Warning", "Connect to Arduino first.")
            return

        if not self.is_live:
            self.is_live = True
            self.live_btn.config(text="⏹ Stop Live View")
            self.current_img = np.zeros((self.PIXELS, self.PIXELS))
            self.serial_conn.reset_input_buffer()
            self.send_command(b'L')
            self.poll_live_data()
        else:
            self.is_live = False
            self.live_btn.config(text="▶ Start Live View")
            self.send_command(b'H') # Stop live scan

    def poll_live_data(self):
        if not self.is_live: return
        
        try:
            bytes_waiting = self.serial_conn.in_waiting
            # Only read blocks of 3 bytes (X, Y, Z)
            bytes_to_read = bytes_waiting - (bytes_waiting % 3) 
            
            if bytes_to_read > 0:
                raw_data = self.serial_conn.read(bytes_to_read)
                data_matrix = np.frombuffer(raw_data, dtype=np.uint8).reshape(-1, 3)
                
                # Instantly map incoming data to their respective XY coordinates
                self.current_img[data_matrix[:, 1], data_matrix[:, 0]] = data_matrix[:, 2]
                self.update_image_plot()
                
        except Exception as e:
            print(f"Serial read error: {e}")

        # Poll again in 30ms for smooth UI performance
        self.root.after(30, self.poll_live_data)

    def collect_data(self):
        self.send_command(b'C')
        print("Data collection started on Arduino...")

    def transfer_data(self):
        if self.is_live:
            messagebox.showinfo("Stop Live View", "Please stop Live View before transferring a static frame.")
            return
            
        self.send_command(b'S')
        raw_bytes = self.serial_conn.read(self.TOTAL_BYTES)
        
        if len(raw_bytes) != self.TOTAL_BYTES:
            messagebox.showwarning("Warning", f"Received {len(raw_bytes)} bytes, expected {self.TOTAL_BYTES}.")
            return
            
        data_matrix = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(-1, 3)
        self.raw_x = data_matrix[:, 0]
        self.raw_y = data_matrix[:, 1]
        self.raw_z = data_matrix[:, 2]
        
        # Populate the image matrix
        self.current_img = np.zeros((self.PIXELS, self.PIXELS))
        x_idx = np.clip(self.raw_x, 0, self.PIXELS - 1)
        y_idx = np.clip(self.raw_y, 0, self.PIXELS - 1)
        self.current_img[y_idx, x_idx] = self.raw_z
        
        messagebox.showinfo("Success", "Data transferred successfully.")
        self.update_image_plot()

    def update_image_plot(self):
        """Applies brightness/contrast and visually updates the canvas without heavy math."""
        c, b = self.contrast.get(), self.brightness.get()
        img_final = c * (self.current_img - 128) + 128 + b
        img_final = np.clip(img_final, 0, 255).astype(np.uint8)

        if self.im_obj is None:
            # First time draw
            self.ax.clear()
            self.ax.set_title(f"{self.PIXELS}x{self.PIXELS} DAQ Image")
            self.ax.axis('off')
            self.im_obj = self.ax.imshow(img_final, cmap='gray', vmin=0, vmax=255, origin='lower')
            self.canvas.draw()
        else:
            # Fast redraw (doesn't rebuild axes)
            self.im_obj.set_data(img_final)
            self.canvas.draw_idle() 

    def save_raw_data(self):
        if self.raw_x is None:
            messagebox.showwarning("Warning", "No static raw data to save. Use 'Collect Full Frame' first.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".npy",
            filetypes=[("NumPy file", "*.npy"), ("All files", "*.*")],
            title="Save Raw Data As"
        )

        if filepath:
            try:
                data_matrix = np.column_stack((self.raw_x, self.raw_y, self.raw_z))
                np.save(filepath, data_matrix)
                messagebox.showinfo("Success", f"Data saved to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save data: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = DAQImageApp(root)
    root.mainloop()

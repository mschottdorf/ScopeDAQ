import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class DAQImageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scanning Image DAQ")
        
        # Data storage
        self.raw_x, self.raw_y, self.raw_z = None, None, None
        self.serial_conn = None
        self.TOTAL_BYTES = 30000 * 3 # Matching Arduino constraints
        
        self.setup_ui()

    def setup_ui(self):
        # --- Control Panel ---
        ctrl_frame = ttk.Frame(self.root, padding=10)
        ctrl_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        ttk.Label(ctrl_frame, text="COM Port (usuallz /dev/ttyACM0):").pack(pady=5)
        self.port_entry = ttk.Entry(ctrl_frame)
        self.port_entry.pack(pady=5)
        self.port_entry.insert(0, "COM3")
        
        ttk.Button(ctrl_frame, text="Connect", command=self.connect_serial).pack(pady=10)
        
        ttk.Separator(ctrl_frame, orient='horizontal').pack(fill='x', pady=10)
        
        ttk.Button(ctrl_frame, text="1. Collect Data", command=self.collect_data).pack(pady=5)
        ttk.Button(ctrl_frame, text="2. Transfer Data", command=self.transfer_data).pack(pady=5)
        ttk.Button(ctrl_frame, text="3. Process & Display", command=self.process_and_display).pack(pady=5)
        ttk.Button(ctrl_frame, text="4. Save Raw Data", command=self.save_raw_data).pack(pady=5)
        
        ttk.Separator(ctrl_frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(ctrl_frame, text="Phase Delays (Samples)").pack()
        
        self.phase_x = tk.IntVar(value=0)
        self.phase_y = tk.IntVar(value=0)
        self.phase_z = tk.IntVar(value=0)
        
        self.create_slider(ctrl_frame, "Phase X:", self.phase_x, 0, 10000)
        self.create_slider(ctrl_frame, "Phase Y:", self.phase_y, 0, 10000)
        self.create_slider(ctrl_frame, "Phase Z:", self.phase_z, 0, 10000)
        
        ttk.Separator(ctrl_frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(ctrl_frame, text="Image Adjustments").pack()
        
        self.contrast = tk.DoubleVar(value=1.0)
        self.brightness = tk.DoubleVar(value=0.0)
        
        self.create_slider(ctrl_frame, "Contrast:", self.contrast, 0.1, 5.0, resolution=0.1)
        self.create_slider(ctrl_frame, "Brightness:", self.brightness, -128, 128)

        # --- Image Display Panel ---
        self.fig, self.ax = plt.subplots(figsize=(5, 5))
        self.ax.set_title("100x100 Reconstructed Image")
        self.ax.axis('off')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def create_slider(self, parent, label_text, variable, vmin, vmax, resolution=1):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=2)
        ttk.Label(frame, text=label_text, width=12).pack(side=tk.LEFT)
        scale = tk.Scale(frame, variable=variable, from_=vmin, to=vmax, 
                         resolution=resolution, orient=tk.HORIZONTAL, 
                         command=lambda e: self.process_and_display())
        scale.pack(side=tk.RIGHT, fill='x', expand=True)

    def connect_serial(self):
        port = self.port_entry.get()
        try:
            self.serial_conn = serial.Serial(port, baudrate=2000000, timeout=5)
            messagebox.showinfo("Success", f"Connected to {port}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect: {e}")

    def collect_data(self):
        if not self.serial_conn: return
        self.serial_conn.write(b'C')
        print("Data collection started on Arduino...")

    def transfer_data(self):
        if not self.serial_conn: return
        self.serial_conn.write(b'S')
        
        raw_bytes = self.serial_conn.read(self.TOTAL_BYTES)
        
        if len(raw_bytes) != self.TOTAL_BYTES:
            messagebox.showwarning("Warning", f"Received {len(raw_bytes)} bytes, expected {self.TOTAL_BYTES}.")
            return
            
        # Reshape data into [30000, 3] array
        data_matrix = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(-1, 3)
        self.raw_x = data_matrix[:, 0]
        self.raw_y = data_matrix[:, 1]
        self.raw_z = data_matrix[:, 2]
        messagebox.showinfo("Success", "Data transferred successfully.")

    def process_and_display(self):
        if self.raw_x is None: return

        px, py, pz = self.phase_x.get(), self.phase_y.get(), self.phase_z.get()
        max_p = max(px, py, pz)
        
        # Calculate valid starting indices to align arrays
        start_x, start_y, start_z = max_p - px, max_p - py, max_p - pz
        end_idx = len(self.raw_x) - max_p
        
        if end_idx <= 0: return

        # Apply phase shifts. Not great...
        x_aligned = self.raw_x[start_x : start_x + end_idx]
        y_aligned = self.raw_y[start_y : start_y + end_idx]
        z_aligned = self.raw_z[start_z : start_z + end_idx]

        # Normalize X and Y space to 0-99for 100 grid
        x_min, x_max = x_aligned.min(), x_aligned.max()
        y_min, y_max = y_aligned.min(), y_aligned.max()
        
        # Prevent division by zero if signal is flat
        if x_max == x_min: x_max = x_min + 1
        if y_max == y_min: y_max = y_min + 1

        x_idx = np.clip(((x_aligned - x_min) / (x_max - x_min) * 99).astype(int), 0, 99)
        y_idx = np.clip(((y_aligned - y_min) / (y_max - y_min) * 99).astype(int), 0, 99)

        # Binning and averaging for duplicate pixels
        img_sum = np.zeros((100, 100))
        img_count = np.zeros((100, 100))

        # Vectorized accumulation
        np.add.at(img_sum, (y_idx, x_idx), z_aligned)
        np.add.at(img_count, (y_idx, x_idx), 1)

        # Average where counts > 0, else 0
        img_avg = np.divide(img_sum, img_count, out=np.zeros_like(img_sum), where=img_count!=0)

        # Apply Contrast and Brightness to Z axis
        # Formula: new_Z = contrast * (old_Z - 128) + 128 + brightness
        c, b = self.contrast.get(), self.brightness.get()
        img_final = c * (img_avg - 128) + 128 + b
        
        # Clip to 0-255 grayscale bounds
        img_final = np.clip(img_final, 0, 255).astype(np.uint8)

        # Render
        self.ax.clear()
        self.ax.set_title("100x100 Reconstructed Image")
        self.ax.axis('off')
        self.ax.imshow(img_final, cmap='gray', vmin=0, vmax=255, origin='lower')
        self.canvas.draw()

    def save_raw_data(self):
        # Check if we actually have data to save
        if self.raw_x is None or self.raw_y is None or self.raw_z is None:
            messagebox.showwarning("Warning", "No raw data available to save. Please transfer data first.")
            return

        # Open a save file dialog
        filepath = filedialog.asksaveasfilename(
            defaultextension=".npy",
            filetypes=[("NumPy file", "*.npy"), ("All files", "*.*")],
            title="Save Raw Data As"
        )

        if filepath:
            try:
                # Re-stack the 1D arrays back into an N x 3 array
                data_matrix = np.column_stack((self.raw_x, self.raw_y, self.raw_z))
                
                # Save as a binary .npy file
                np.save(filepath, data_matrix)
                
                messagebox.showinfo("Success", f"Raw data successfully saved to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save data: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = DAQImageApp(root)
    root.mainloop()

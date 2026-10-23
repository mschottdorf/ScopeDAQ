import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import datetime
import socket

# LCARS Palette (Star Trek TNG Style)
LCARS_BLACK = "#000000"
LCARS_ORANGE = "#FF9900"
LCARS_YELLOW = "#FFFF66"
LCARS_PEACH = "#FFCC99"
LCARS_PURPLE = "#CC99CC"
LCARS_BLUE = "#3399CC"
LCARS_DK_BLUE = "#336699"
LCARS_MAROON = "#996666"
LCARS_WHITE = "#FFFFFF"

class LCARSButton(tk.Canvas):
    """A custom rounded 'pill' button for authentic LCARS style."""
    def __init__(self, parent, text, color, command, radius=15, height=32, **kwargs):
        super().__init__(parent, bg=LCARS_BLACK, highlightthickness=0, height=height, **kwargs)
        self.color = color
        self.text = text
        self.command = command
        self.radius = radius
        self.height = height

        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event=None):
        width = self.winfo_width()
        height = self.height
        radius = self.radius

        self.delete("all")
        if width < 2 * radius:
             radius = width / 2
        
        # Draw rounded pill shape
        self.create_arc(0, 0, 2 * radius, height, start=90, extent=180, fill=self.color, outline="")
        self.create_rectangle(radius, 0, width - radius, height, fill=self.color, outline="")
        self.create_arc(width - 2 * radius, 0, width, height, start=270, extent=180, fill=self.color, outline="")

        # Draw label text
        self.create_text(width / 2, height / 2, text=self.text, fill=LCARS_BLACK, font=("Helvetica", 9, "bold"), justify="center")

    def _on_click(self, event):
        if self.command:
            self.command()

class LCARSSeparator(tk.Canvas):
    """Draws classic LCARS curved elbows and horizontal panel bars."""
    def __init__(self, parent, height=25, color=LCARS_ORANGE, curve_side="left", **kwargs):
        super().__init__(parent, bg=LCARS_BLACK, height=height, highlightthickness=0, **kwargs)
        self.color = color
        self.curve_side = curve_side
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        width = self.winfo_width()
        height = self.winfo_height()
        self.delete("all")
        
        # Horizontal accent bar with curved end
        if self.curve_side == "left":
            self.create_arc(0, 0, height*2, height*2, start=90, extent=180, fill=self.color, outline="")
            self.create_rectangle(height, 0, width, height, fill=self.color, outline="")
        elif self.curve_side == "right":
            self.create_arc(width - height*2, 0, width, height*2, start=270, extent=180, fill=self.color, outline="")
            self.create_rectangle(0, 0, width - height, height, fill=self.color, outline="")
        else:
            self.create_rectangle(0, 0, width, height, fill=self.color, outline="")

class DAQImageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LCARS // LIGHT SHEET MICROSCOPE CONSOLE")
        self.root.geometry("1250x880")
        self.root.minsize(1000, 750)
        self.root.configure(bg=LCARS_BLACK)

        self.is_fullscreen = False
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

        # State & Data storage
        self.raw_x, self.raw_y, self.raw_z = None, None, None
        self.serial_conn = None
        self.is_live = False

        # Core Image Array Constants
        self.PIXELS = 128
        self.TOTAL_PIXELS = self.PIXELS * self.PIXELS
        self.TOTAL_BYTES = self.TOTAL_PIXELS * 3 

        # High-Speed Live Variables
        self.current_img = np.zeros((self.PIXELS, self.PIXELS))
        self.im_obj = None 
        self.live_ptr = 0 
        self.current_cmap = 'magma'

        # Initialize adjustment variables first
        self.zoom = tk.IntVar(value=100)
        self.contrast = tk.DoubleVar(value=1.0)
        self.brightness = tk.DoubleVar(value=0.0)
        self.flip_lr = tk.BooleanVar(value=False)
        self.flip_tb = tk.BooleanVar(value=False)

        self.setup_ui()

    def setup_ui(self):
        # ==========================================
        # BLOCK 1: TOP BLOCK (Status, Connect, Log)
        # ==========================================
        block1_frame = tk.Frame(self.root, bg=LCARS_BLACK)
        block1_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 5))

        # Status & Header Bar
        status_header = tk.Frame(block1_frame, bg=LCARS_BLACK)
        status_header.pack(fill=tk.X, pady=(0, 5))

        tk.Label(status_header, text="LCARS 105", fg=LCARS_WHITE, bg=LCARS_BLACK, font=("Helvetica", 9)).pack(side=tk.LEFT)
        LCARSButton(status_header, text="MICROSCOPE CONTROL", color=LCARS_PURPLE, command=None, height=28, width=200).pack(side=tk.LEFT, padx=10)
        
        self.stardate_label = tk.Label(status_header, text="", fg=LCARS_BLUE, bg=LCARS_BLACK, font=("Helvetica", 9, "bold"))
        self.stardate_label.pack(side=tk.LEFT, padx=10)
        self.update_stardate()

        self.ip_label = tk.Label(status_header, text=f"IP: {self.get_ip()}", fg=LCARS_PEACH, bg=LCARS_BLACK, font=("Helvetica", 9))
        self.ip_label.pack(side=tk.LEFT, padx=10)

        LCARSButton(status_header, text="EXIT SYSTEM", color=LCARS_MAROON, command=self.exit_app, height=28, width=110).pack(side=tk.RIGHT)

        # LCARS Curved Separator 1
        LCARSSeparator(block1_frame, height=18, color=LCARS_ORANGE, curve_side="left").pack(fill=tk.X, pady=2)

        # Top Content: Connect Panel & Event Log Side-by-Side
        top_content = tk.Frame(block1_frame, bg=LCARS_BLACK)
        top_content.pack(fill=tk.X, pady=5)

        # Connect Sub-panel (pack_propagate removed to prevent button cutoff)
        connect_panel = tk.Frame(top_content, bg="#0a0a0a", bd=1, relief=tk.SOLID, width=280)
        connect_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        tk.Label(connect_panel, text="SERIAL LINK", fg=LCARS_PEACH, bg="#0a0a0a", font=("Helvetica", 9, "bold")).pack(anchor='w', padx=8, pady=5)
        tk.Label(connect_panel, text="COM PORT:", fg=LCARS_WHITE, bg="#0a0a0a", font=("Helvetica", 8)).pack(anchor='w', padx=8)
        
        self.port_entry = tk.Entry(connect_panel, bg="#1a1a1a", fg=LCARS_PEACH, insertbackground=LCARS_PEACH, relief=tk.FLAT, font=("Helvetica", 9))
        self.port_entry.pack(fill='x', padx=8, pady=4)
        self.port_entry.insert(0, "/dev/ttyACM0")
        
        LCARSButton(connect_panel, text="INITIALIZE CONNECTION", color=LCARS_PEACH, command=self.connect_serial, height=30, width=250).pack(padx=8, pady=8)

        # Event Log Sub-panel
        log_panel = tk.Frame(top_content, bg="#0a0a0a", bd=1, relief=tk.SOLID)
        log_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(log_panel, text="EVENT LOG:", fg=LCARS_WHITE, bg="#0a0a0a", font=("Helvetica", 9, "bold")).pack(anchor='w', padx=8, pady=4)
        self.console_text = tk.Text(log_panel, height=4, state='disabled', bg=LCARS_BLACK, fg=LCARS_PURPLE, font=("Helvetica", 9), relief=tk.FLAT, selectbackground="#333333")
        self.console_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.log_to_console("LCARS optical scanning subsystem online.")

        # ==========================================
        # BLOCK 2: MIDDLE BLOCK (Controls & Image View)
        # ==========================================
        block2_frame = tk.Frame(self.root, bg=LCARS_BLACK)
        block2_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        # LCARS Curved Separator 2
        LCARSSeparator(block2_frame, height=18, color=LCARS_BLUE, curve_side="right").pack(fill=tk.X, pady=2)

        middle_content = tk.Frame(block2_frame, bg=LCARS_BLACK)
        middle_content.pack(fill=tk.BOTH, expand=True, pady=5)

        # Left Column: Core Functions (Scan Modes, Acquisition, Flips, Colormaps)
        controls_col = tk.Frame(middle_content, bg=LCARS_BLACK, width=280)
        controls_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        controls_col.pack_propagate(False)

        tk.Label(controls_col, text="SUBSYSTEM SCAN MODES", fg=LCARS_YELLOW, bg=LCARS_BLACK, font=("Helvetica", 9, "bold")).pack(anchor='w', pady=2)
        LCARSButton(controls_col, text="SCAN X AXIS", color=LCARS_ORANGE, command=lambda: self.send_command(b'X'), height=28, width=270).pack(pady=2)
        LCARSButton(controls_col, text="SCAN Y AXIS", color=LCARS_ORANGE, command=lambda: self.send_command(b'Y'), height=28, width=270).pack(pady=2)
        LCARSButton(controls_col, text="SLOW X+Y (128x128)", color=LCARS_YELLOW, command=lambda: self.send_command(b'B'), height=28, width=270).pack(pady=2)
        LCARSButton(controls_col, text="FAST X+Y (TEK MODE)", color=LCARS_YELLOW, command=lambda: self.send_command(b'F'), height=28, width=270).pack(pady=2)
        LCARSButton(controls_col, text="HALT MOTION", color=LCARS_MAROON, command=lambda: self.send_command(b'H'), height=28, width=270).pack(pady=4)

        tk.Label(controls_col, text="DATA ACQUISITION", fg=LCARS_PEACH, bg=LCARS_BLACK, font=("Helvetica", 9, "bold")).pack(anchor='w', pady=(4, 2))
        self.live_btn_ui = LCARSButton(controls_col, text="▶ START LIVE FEED", color=LCARS_PURPLE, command=self.toggle_live, height=30, width=270)
        self.live_btn_ui.pack(pady=2)
        LCARSButton(controls_col, text="1. COLLECT FULL FRAME", color=LCARS_DK_BLUE, command=self.collect_data, height=28, width=270).pack(pady=2)
        LCARSButton(controls_col, text="2. TRANSFER FRAME DATA", color=LCARS_DK_BLUE, command=self.transfer_data, height=28, width=270).pack(pady=4)

        tk.Label(controls_col, text="SPATIAL ORIENTATION", fg=LCARS_BLUE, bg=LCARS_BLACK, font=("Helvetica", 9, "bold")).pack(anchor='w', pady=(4, 2))
        
        flips_sub = tk.Frame(controls_col, bg=LCARS_BLACK)
        flips_sub.pack(fill=tk.X, pady=2)
        
        # Clickable LCARS Buttons for L/R and T/B orientation toggles
        self.btn_flip_lr = LCARSButton(flips_sub, text="FLIP L/R", color=LCARS_DK_BLUE, command=self.toggle_flip_lr, height=28, width=130)
        self.btn_flip_lr.pack(side=tk.LEFT, padx=(0, 5), expand=True)
        
        self.btn_flip_tb = LCARSButton(flips_sub, text="FLIP T/B", color=LCARS_DK_BLUE, command=self.toggle_flip_tb, height=28, width=130)
        self.btn_flip_tb.pack(side=tk.RIGHT, padx=(5, 0), expand=True)

        tk.Label(controls_col, text="DISPLAY COLORMAP", fg=LCARS_PEACH, bg=LCARS_BLACK, font=("Helvetica", 9, "bold")).pack(anchor='w', pady=(4, 2))
        LCARSButton(controls_col, text="MAGMA (DEFAULT)", color=LCARS_PURPLE, command=lambda: self.set_cmap('magma'), height=26, width=270).pack(pady=2)
        LCARSButton(controls_col, text="GRAYSCALE", color=LCARS_DK_BLUE, command=lambda: self.set_cmap('gray'), height=26, width=270).pack(pady=2)
        LCARSButton(controls_col, text="JET COLOR", color=LCARS_BLUE, command=lambda: self.set_cmap('jet'), height=26, width=270).pack(pady=2)

        # Right Column: Matplotlib Optical Reconstruction Display
        display_col = tk.Frame(middle_content, bg="#0a0a0a", bd=1, relief=tk.SOLID)
        display_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        plt.style.use('dark_background')
        self.fig, self.ax = plt.subplots(figsize=(6, 6), layout='constrained')
        self.fig.patch.set_facecolor("#0a0a0a")
        self.ax.set_facecolor(LCARS_BLACK)
        self.ax.set_title("128x128 OPTICAL RECONSTRUCTION ARRAY", color=LCARS_ORANGE, fontsize=10, fontweight='bold')
        self.ax.axis('off')

        self.canvas = FigureCanvasTkAgg(self.fig, master=display_col)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.update_image_plot()

        # ==========================================
        # BLOCK 3: BOTTOM BLOCK (Transporter Sliders & Aux)
        # ==========================================
        block3_frame = tk.Frame(self.root, bg=LCARS_BLACK)
        block3_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5, 10))

        # LCARS Curved Separator 3
        LCARSSeparator(block3_frame, height=18, color=LCARS_PEACH, curve_side="left").pack(fill=tk.X, pady=2)

        bottom_content = tk.Frame(block3_frame, bg="#0a0a0a", bd=1, relief=tk.SOLID)
        bottom_content.pack(fill=tk.X, pady=5, ipadx=5, ipady=5)

        tk.Label(bottom_content, text="TRANSPORTER TERMINAL // CALIBRATION SLIDERS", fg=LCARS_ORANGE, bg="#0a0a0a", font=("Helvetica", 9, "bold")).pack(anchor='w', padx=10, pady=4)

        # Three long transporter-style sliders laid out horizontally across the bottom
        sliders_grid = tk.Frame(bottom_content, bg="#0a0a0a")
        sliders_grid.pack(fill=tk.X, padx=10, pady=4)

        self.create_transporter_slider(sliders_grid, "ZOOM (%)", self.zoom, 1, 100, color=LCARS_ORANGE, command=self.update_zoom)
        self.create_transporter_slider(sliders_grid, "CONTRAST", self.contrast, 0.1, 5.0, resolution=0.1, color=LCARS_YELLOW, command=self.update_image_plot)
        self.create_transporter_slider(sliders_grid, "BRIGHTNESS", self.brightness, -128, 128, color=LCARS_BLUE, command=self.update_image_plot)

        # Auxiliary Actions at bottom (Save Raw Data)
        aux_row = tk.Frame(bottom_content, bg="#0a0a0a")
        aux_row.pack(fill=tk.X, padx=10, pady=(8, 4))

        LCARSButton(aux_row, text="EXPORT RAW MATRIX (.NPY)", color=LCARS_DK_BLUE, command=self.save_raw_data, height=32, width=250).pack(side=tk.LEFT)
        tk.Label(aux_row, text="SYS.ACTIVE // LINK STABLE", fg=LCARS_PURPLE, bg="#0a0a0a", font=("Helvetica", 8, "italic")).pack(side=tk.RIGHT, padx=10)

    def create_transporter_slider(self, parent, label_text, variable, vmin, vmax, color, resolution=1, command=None):
        """Creates a long horizontal TNG transporter-style slider control."""
        frame = tk.Frame(parent, bg="#0a0a0a", pady=2)
        frame.pack(fill='x', expand=True, pady=2)
        
        header_sub = tk.Frame(frame, bg="#0a0a0a")
        header_sub.pack(fill='x', padx=2)
        tk.Label(header_sub, text=label_text, fg=color, bg="#0a0a0a", font=("Helvetica", 8, "bold")).pack(side=tk.LEFT)
        
        scale = tk.Scale(
            frame, variable=variable, from_=vmin, to=vmax, 
            resolution=resolution, orient=tk.HORIZONTAL, 
            command=lambda e: command() if command else None,
            bg="#0a0a0a", fg=color, highlightthickness=0, 
            troughcolor="#1a1a1a", sliderrelief=tk.FLAT, bd=0
        )
        scale.pack(fill='x', expand=True, padx=2)

    # --- Utility & Core Logic Methods ---
    def update_stardate(self):
        now = datetime.datetime.now()
        stardate = f"STAR DATE {now.year}.{now.month:02d}.{now.day:02d} {now.hour:02d}:{now.minute:02d}:{now.second:02d}"
        self.stardate_label.config(text=stardate)
        self.root.after(1000, self.update_stardate)

    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except:
            ip = "127.0.0.1"
        return ip

    def log_to_console(self, text):
        self.console_text.config(state='normal')
        self.console_text.insert(tk.END, f"{text}\n")
        self.console_text.config(state='disabled')
        self.console_text.see(tk.END)

    def exit_app(self):
        if self.serial_conn:
            try:
                self.send_command(b'H')
                self.serial_conn.close()
            except:
                pass
        self.root.quit()

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
            self.update_zoom()
            self.log_to_console(f"SERIAL: Connected to optical link {port}.")
        except Exception as e:
            self.log_to_console(f"SERIAL ERROR: Connection failed: {e}")
            messagebox.showerror("LCARS ERROR", f"Could not connect: {e}")

    def send_command(self, cmd):
        if not self.serial_conn:
            self.log_to_console("SERIAL WARNING: Subsystem offline. Connect port first.")
            return
        self.serial_conn.write(cmd)
        self.log_to_console(f"SERIAL TRANSMIT: {cmd.decode()}")
        
    def update_zoom(self):
        if self.serial_conn:
            val = int(0.6 * self.zoom.get())
            self.serial_conn.write(b'Z' + bytes([val]))
            self.log_to_console(f"TRANSMIT: Zoom factor set to {val}")

    def toggle_live(self):
        if not self.serial_conn:
            self.log_to_console("LIVE WARNING: Connect serial link first.")
            return

        if not self.is_live:
            self.is_live = True
            self.live_btn_ui.text = "⏹ STOP LIVE FEED"
            self.live_btn_ui.color = LCARS_MAROON
            self.live_btn_ui._redraw()
            self.current_img = np.zeros((self.PIXELS, self.PIXELS))
            self.live_ptr = 0 
            self.serial_conn.reset_input_buffer()
            self.send_command(b'L')
            self.poll_live_data()
        else:
            self.is_live = False
            self.live_btn_ui.text = "▶ START LIVE FEED"
            self.live_btn_ui.color = LCARS_PURPLE
            self.live_btn_ui._redraw()
            self.send_command(b'H')

    def poll_live_data(self):
        if not self.is_live: return
        
        try:
            bytes_waiting = self.serial_conn.in_waiting
            if bytes_waiting > 0:
                raw_data = self.serial_conn.read(bytes_waiting)
                data_array = np.frombuffer(raw_data, dtype=np.uint8)
                n_bytes = len(data_array)
                
                flat_img = self.current_img.ravel()
                
                if self.live_ptr + n_bytes > self.TOTAL_PIXELS:
                    space_left = self.TOTAL_PIXELS - self.live_ptr
                    flat_img[self.live_ptr:] = data_array[:space_left]
                    
                    remaining = n_bytes - space_left
                    if remaining >= self.TOTAL_PIXELS:
                        data_array = data_array[-self.TOTAL_PIXELS:]
                        remaining = self.TOTAL_PIXELS
                        
                    flat_img[:remaining] = data_array[-remaining:]
                    self.live_ptr = remaining
                else:
                    flat_img[self.live_ptr : self.live_ptr + n_bytes] = data_array
                    self.live_ptr += n_bytes
                
                self.current_img = flat_img.reshape((self.PIXELS, self.PIXELS))
                self.update_image_plot()
                
        except Exception as e:
            self.log_to_console(f"SERIAL READ ERROR: {e}")

        self.root.after(30, self.poll_live_data)

    def collect_data(self):
        if self.serial_conn:
            self.serial_conn.reset_input_buffer()
        self.send_command(b'C')
        self.log_to_console("Data collection initiated on hardware controller...")

    def transfer_data(self):
        if self.is_live:
            self.log_to_console("TRANSFER INFO: Stop Live Feed before transferring static frame.")
            return
            
        if self.serial_conn:
            self.serial_conn.reset_input_buffer()
            
        self.send_command(b'S')
        raw_bytes = self.serial_conn.read(self.TOTAL_BYTES)
        
        if len(raw_bytes) != self.TOTAL_BYTES:
            self.log_to_console(f"TRANSFER WARNING: Received {len(raw_bytes)} bytes, expected {self.TOTAL_BYTES}.")
            return
            
        data_matrix = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(-1, 3)
        self.raw_x = data_matrix[:, 0]
        self.raw_y = data_matrix[:, 1]
        self.raw_z = data_matrix[:, 2]
        
        self.current_img = np.zeros((self.PIXELS, self.PIXELS))
        x_idx = np.clip(self.raw_x, 0, self.PIXELS - 1)
        y_idx = np.clip(self.raw_y, 0, self.PIXELS - 1)
        self.current_img[y_idx, x_idx] = self.raw_z
        
        self.log_to_console("TRANSFER: Full optical frame transferred successfully.")
        self.update_image_plot()

    def toggle_flip_lr(self):
        val = not self.flip_lr.get()
        self.flip_lr.set(val)
        self.btn_flip_lr.color = LCARS_ORANGE if val else LCARS_DK_BLUE
        self.btn_flip_lr._redraw()
        self.update_image_plot()
        self.log_to_console(f"ORIENTATION: Horizontal flip {'enabled' if val else 'disabled'}.")

    def toggle_flip_tb(self):
        val = not self.flip_tb.get()
        self.flip_tb.set(val)
        self.btn_flip_tb.color = LCARS_ORANGE if val else LCARS_DK_BLUE
        self.btn_flip_tb._redraw()
        self.update_image_plot()
        self.log_to_console(f"ORIENTATION: Vertical flip {'enabled' if val else 'disabled'}.")

    def set_cmap(self, cmap_name):
        self.current_cmap = cmap_name
        self.log_to_console(f"DISPLAY: Colormap switched to {cmap_name.upper()}.")
        self.update_image_plot()

    def update_image_plot(self):
        c, b = self.contrast.get(), self.brightness.get()
        img_final = c * (self.current_img - 128) + 128 + b
        img_final = np.clip(img_final, 0, 255).astype(np.uint8)

        if self.flip_lr.get():
            img_final = np.fliplr(img_final)
        if self.flip_tb.get():
            img_final = np.flipud(img_final)

        if self.im_obj is None:
            self.ax.clear()
            self.ax.set_facecolor(LCARS_BLACK)
            self.ax.axis('off')
            self.im_obj = self.ax.imshow(img_final, cmap=self.current_cmap, vmin=0, vmax=255, origin='lower')
            self.canvas.draw()
        else:
            self.im_obj.set_cmap(self.current_cmap)
            self.im_obj.set_data(img_final)
            self.canvas.draw_idle() 

    def save_raw_data(self):
        if self.raw_x is None:
            self.log_to_console("SAVE WARNING: No buffer available. Execute 'Collect Frame' first.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".npy",
            filetypes=[("NumPy Matrix (*.npy)", "*.npy"), ("All Files", "*.*")],
            title="Export Optical Matrix"
        )

        if filepath:
            try:
                data_matrix = np.column_stack((self.raw_x, self.raw_y, self.raw_z))
                np.save(filepath, data_matrix)
                self.log_to_console(f"EXPORT SUCCESS: Matrix saved to {filepath}")
            except Exception as e:
                self.log_to_console(f"EXPORT ERROR: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style(root)
    style.theme_use('clam')
    app = DAQImageApp(root)
    root.mainloop()

import sys
import time
import numpy as np
import tifffile
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QComboBox, QProgressBar, QMessageBox, QGroupBox, 
                             QFormLayout, QTextEdit, QSlider, QSpinBox, 
                             QFileDialog)
from PyQt5.QtCore import Qt, QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from vmbpy import VmbSystem, Camera, FrameStatus, AllocationMode, VmbFeatureError

class CameraGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Allied Vision High-Speed Acquirer")
        self.resize(1100, 1000)
        
        # Camera State Variables
        self.vmb = VmbSystem.get_instance()
        self.vmb.__enter__() 
        self.cam = None
        self.ram_stack = None
        self.frames_acquired = 0
        self.target_frames = 0
        self.is_live = False  
        
        # --- NEW: Thread Decoupling Variables ---
        self.live_frame = None
        self.live_timer = QTimer()
        self.live_timer.timeout.connect(self.render_live_frame)
        self.live_timer.setInterval(33)  # Pull frames at ~30 FPS (33ms)
        
        # Plotting Variables
        self.im = None
        self.cbar = None
        self.last_img = None  
        self.hist_stairs = None # --- NEW: Fast histogram updating ---
        
        self.init_ui()
        self.refresh_cameras()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Panel
        control_panel = QVBoxLayout()
        main_layout.addLayout(control_panel, stretch=1)

        # 1. Camera Management
        cam_group = QGroupBox("1. Camera Management")
        cam_layout = QVBoxLayout()
        self.cam_combo = QComboBox()
        cam_layout.addWidget(self.cam_combo)
        
        btns_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.clicked.connect(self.refresh_cameras)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_camera)
        btns_layout.addWidget(self.refresh_btn)
        btns_layout.addWidget(self.connect_btn)
        cam_layout.addLayout(btns_layout)
        
        self.query_btn = QPushButton("Query Current Device Settings")
        self.query_btn.clicked.connect(self.query_settings)
        self.query_btn.setEnabled(False)
        cam_layout.addWidget(self.query_btn)
        
        self.cam_info_text = QTextEdit()
        self.cam_info_text.setReadOnly(True)
        self.cam_info_text.setMaximumHeight(150)
        cam_layout.addWidget(self.cam_info_text)
        cam_group.setLayout(cam_layout)
        control_panel.addWidget(cam_group)

        # 2. Settings
        settings_group = QGroupBox("2. Camera Settings")
        settings_layout = QFormLayout()
        self.exp_input = QLineEdit("10.0")
        settings_layout.addRow("Exposure (ms):", self.exp_input)
        self.gain_input = QLineEdit("0.0")
        settings_layout.addRow("Gain (dB):", self.gain_input)
        self.roi_combo = QComboBox()
        self.roi_combo.addItems(["Full", "1/4", "1/16"])
        settings_layout.addRow("Sensor Area:", self.roi_combo)
        self.format_combo = QComboBox()
        settings_layout.addRow("Pixel Format:", self.format_combo)
        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.clicked.connect(self.apply_settings)
        self.apply_btn.setEnabled(False)
        settings_layout.addWidget(self.apply_btn)
        self.fps_label = QLabel("Estimated Max FPS: --")
        settings_layout.addWidget(self.fps_label)
        settings_group.setLayout(settings_layout)
        control_panel.addWidget(settings_group)

        # 3. Acquisition
        acq_group = QGroupBox("3. Acquisition")
        acq_layout = QVBoxLayout()
        self.live_btn = QPushButton("Start Live View")
        self.live_btn.setCheckable(True)
        self.live_btn.clicked.connect(self.toggle_live_view)
        self.live_btn.setEnabled(False)
        acq_layout.addWidget(self.live_btn)

        self.single_btn = QPushButton("Grab Single Frame")
        self.single_btn.clicked.connect(self.grab_single)
        self.single_btn.setEnabled(False)
        acq_layout.addWidget(self.single_btn)
        
        acq_layout.addWidget(QLabel("Frames to RAM:"))
        self.frames_input = QLineEdit("100")
        acq_layout.addWidget(self.frames_input)
        
        self.fast_grab_btn = QPushButton("Fast Grab to RAM")
        self.fast_grab_btn.setStyleSheet("background-color: #27ae60; color: white;")
        self.fast_grab_btn.clicked.connect(self.fast_grab)
        self.fast_grab_btn.setEnabled(False)
        acq_layout.addWidget(self.fast_grab_btn)
        
        self.progress_bar = QProgressBar()
        acq_layout.addWidget(self.progress_bar)
        
        self.save_btn = QPushButton("Save RAM Stack")
        self.save_btn.clicked.connect(self.save_stack)
        self.save_btn.setEnabled(False)
        acq_layout.addWidget(self.save_btn)
        acq_group.setLayout(acq_layout)
        control_panel.addWidget(acq_group)
        
        # 4. Display Settings
        disp_group = QGroupBox("4. Display Settings")
        disp_layout = QFormLayout()
        self.vmin_slider = QSlider(Qt.Horizontal)
        self.vmin_slider.setRange(0, 4095)
        self.vmin_slider.setValue(0)
        self.vmin_slider.valueChanged.connect(self.refresh_display)
        
        self.vmax_slider = QSlider(Qt.Horizontal)
        self.vmax_slider.setRange(0, 4095)
        self.vmax_slider.setValue(255)
        self.vmax_slider.valueChanged.connect(self.refresh_display)
        
        self.bin_width_spin = QSpinBox()
        self.bin_width_spin.setRange(1, 256)
        self.bin_width_spin.setValue(1) 
        self.bin_width_spin.valueChanged.connect(self.refresh_display)
        
        disp_layout.addRow("Preview Min Int:", self.vmin_slider)
        disp_layout.addRow("Preview Max Int:", self.vmax_slider)
        disp_layout.addRow("Hist Bin Width:", self.bin_width_spin)
        disp_group.setLayout(disp_layout)
        control_panel.addWidget(disp_group)
        
        control_panel.addStretch()

        # Right Panel: Plotting Grid
        self.figure = plt.figure()
        gs = gridspec.GridSpec(3, 2, height_ratios=[4, 1.2, 1.8])
        self.ax_img = self.figure.add_subplot(gs[0, :])
        self.ax_hist = self.figure.add_subplot(gs[1, :])
        self.ax_first = self.figure.add_subplot(gs[2, 0])
        self.ax_last = self.figure.add_subplot(gs[2, 1])
        
        self.ax_img.axis('off')
        self.ax_first.axis('off')
        self.ax_last.axis('off')
        self.ax_first.set_title("First RAM Frame", fontsize=10)
        self.ax_last.set_title("Last RAM Frame", fontsize=10)
        
        self.canvas = FigureCanvas(self.figure)
        main_layout.addWidget(self.canvas, stretch=3)
        self.figure.tight_layout()

    def refresh_cameras(self):
        self.cam_combo.clear()
        cams = self.vmb.get_all_cameras()
        if not cams:
            self.cam_combo.addItem("No cameras found")
            return
        for camera in cams:
            self.cam_combo.addItem(f"{camera.get_id()} ({camera.get_model()})", camera.get_id())

    def connect_camera(self):
        cam_id = self.cam_combo.currentData()
        if not cam_id: return
        if self.cam: 
            try:
                self.cam.__exit__(None, None, None)
            except: pass
        try:
            self.cam = self.vmb.get_camera_by_id(cam_id)
            self.cam.__enter__()
            self.query_settings()
            self.apply_btn.setEnabled(True)
            self.single_btn.setEnabled(True)
            self.fast_grab_btn.setEnabled(True)
            self.live_btn.setEnabled(True)
            self.query_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def query_settings(self):
        if not self.cam: return
        try:
            report = ["--- Current Device State ---"]
            try: 
                exp = self.cam.get_feature_by_name("ExposureTime").get()
            except VmbFeatureError: 
                try: exp = self.cam.get_feature_by_name("ExposureTimeAbs").get()
                except VmbFeatureError: exp = "Unknown"
            
            if isinstance(exp, float): report.append(f"Exposure: {exp/1000.0:.3f} ms")
            else: report.append(f"Exposure: {exp}")
            
            try: gain = self.cam.get_feature_by_name("Gain").get()
            except VmbFeatureError: 
                try: gain = self.cam.get_feature_by_name("GainRaw").get()
                except VmbFeatureError: gain = "Not Found / Locked"
            report.append(f"Gain: {gain}")

            feats = ["Width", "Height", "OffsetX", "OffsetY", "PixelFormat"]
            for f in feats:
                try:
                    val = self.cam.get_feature_by_name(f).get()
                    report.append(f"{f}: {val}")
                except VmbFeatureError:
                    report.append(f"{f}: Not Found")
            
            try:
                pf_feature = self.cam.get_feature_by_name("PixelFormat")
                available_formats = [str(entry) for entry in pf_feature.get_available_entries()]
                self.format_combo.clear()
                self.format_combo.addItems(available_formats)
                current_fmt = str(pf_feature.get())
                max_intensity = 255 if "8" in current_fmt else 4095
                self.vmax_slider.setValue(max_intensity)
            except VmbFeatureError:
                pass
            
            self.cam_info_text.setText("\n".join(report))
            self.update_fps_estimate()
        except Exception as e:
            self.cam_info_text.setText(f"Query Error: {e}")

    def update_plot(self, img_array):
        self.last_img = img_array
        vmin = self.vmin_slider.value()
        vmax = self.vmax_slider.value()

        if self.im is None:
            self.im = self.ax_img.imshow(img_array, cmap='inferno', vmin=vmin, vmax=vmax)
            self.cbar = self.figure.colorbar(self.im, ax=self.ax_img, fraction=0.046, pad=0.04)
            img_min, img_max = int(np.min(img_array)), int(np.max(img_array))
            self.vmin_slider.setValue(img_min)
            self.vmax_slider.setValue(img_max)
        else:
            self.im.set_data(img_array)
            self.im.set_clim(vmin=vmin, vmax=vmax)

        self.refresh_display()

    def refresh_display(self):
        if self.last_img is None: return
        vmin = self.vmin_slider.value()
        vmax = self.vmax_slider.value()
        if vmin >= vmax: vmax = vmin + 1 
        
        if self.im is not None:
            self.im.set_clim(vmin=vmin, vmax=vmax)

        # --- NEW: Fast Histogram Generation ---
        max_val = 255 if self.last_img.dtype == np.uint8 else 4095
        bin_w = self.bin_width_spin.value()
        bins = np.arange(0, max_val + bin_w + 1, bin_w)
        
        # Use numpy for math (much faster than matplotlib hist)
        counts, edges = np.histogram(self.last_img.ravel(), bins=bins)
        
        # Initialize stairs on first run, otherwise just update data
        if self.hist_stairs is None:
            self.ax_hist.clear()
            self.hist_stairs = self.ax_hist.stairs(counts, edges, fill=True, color='gray', alpha=0.7)
            self.ax_hist.set_xlim(0, max_val)
        else:
            self.hist_stairs.set_data(counts, edges)
            # Dynamically adjust Y axis to prevent clipping
            if counts.max() > 0:
                self.ax_hist.set_ylim(0, counts.max() * 1.1)

        self.canvas.draw_idle()

    # --- NEW: QTimer rendering method on Main Thread ---
    def render_live_frame(self):
        if self.live_frame is not None:
            self.update_plot(self.live_frame)
            self.live_frame = None  # Consume the frame

    def async_handler(self, cam: Camera, stream, frame):
        if frame.get_status() == FrameStatus.Complete:
            img = frame.as_numpy_ndarray().copy().squeeze()
            if self.is_live:
                # --- MODIFIED: Instantly pass to main thread, don't plot here ---
                self.live_frame = img 
            elif self.frames_acquired < self.target_frames:
                self.ram_stack[self.frames_acquired] = img
                self.frames_acquired += 1
        cam.queue_frame(frame)

    def toggle_live_view(self):
        if not self.cam: return
        if self.live_btn.isChecked():
            self.is_live = True
            self.live_btn.setText("Stop Live View")
            self.live_btn.setStyleSheet("background-color: #e74c3c; color: white;")
            self.fast_grab_btn.setEnabled(False)
            self.apply_btn.setEnabled(False)
            self.live_timer.start() # Start UI poller
            self.cam.start_streaming(handler=self.async_handler, buffer_count=5)
        else:
            self.is_live = False
            self.live_timer.stop() # Stop UI poller
            self.live_btn.setText("Start Live View")
            self.live_btn.setStyleSheet("")
            try:
                self.cam.stop_streaming()
            except: pass
            self.fast_grab_btn.setEnabled(True)
            self.apply_btn.setEnabled(True)

    def apply_settings(self):
        if not self.cam: return
        errors = [] 
        try:
            exposure_us = float(self.exp_input.text()) * 1000.0
            try: self.cam.get_feature_by_name("ExposureTime").set(exposure_us)
            except VmbFeatureError: self.cam.get_feature_by_name("ExposureTimeAbs").set(exposure_us)
        except Exception as e: errors.append(f"Exposure: {e}")

        try:
            gain_val = float(self.gain_input.text())
            try: self.cam.get_feature_by_name("Gain").set(gain_val)
            except VmbFeatureError: self.cam.get_feature_by_name("GainRaw").set(gain_val)
        except Exception as e: errors.append(f"Gain: Error.")

        try:
            fmt = self.format_combo.currentText()
            if fmt: self.cam.get_feature_by_name("PixelFormat").set(fmt)
        except Exception as e: errors.append(f"PixelFormat: {e}")

        try:
            max_w = self.cam.get_feature_by_name("WidthMax").get()
            max_h = self.cam.get_feature_by_name("HeightMax").get()
            roi_mode = self.roi_combo.currentText()
            self.cam.get_feature_by_name("OffsetX").set(0)
            self.cam.get_feature_by_name("OffsetY").set(0)
            if roi_mode == "Full": w, h, ox, oy = max_w, max_h, 0, 0
            elif roi_mode == "1/4":
                w, h = max_w // 2, max_h // 2
                ox, oy = w // 2, h // 2
            else: 
                w, h = max_w // 4, max_h // 4
                ox, oy = int(max_w * (3/8)), int(max_h * (3/8))
            inc_w = self.cam.get_feature_by_name("Width").get_increment()
            inc_h = self.cam.get_feature_by_name("Height").get_increment()
            inc_ox = self.cam.get_feature_by_name("OffsetX").get_increment()
            inc_oy = self.cam.get_feature_by_name("OffsetY").get_increment()
            w, h = (w // inc_w) * inc_w, (h // inc_h) * inc_h
            self.cam.get_feature_by_name("Width").set(w)
            self.cam.get_feature_by_name("Height").set(h)
            self.cam.get_feature_by_name("OffsetX").set((ox // inc_ox) * inc_ox)
            self.cam.get_feature_by_name("OffsetY").set((oy // inc_oy) * inc_oy)
        except Exception as e: errors.append(f"ROI Geometry: {e}")

        if errors: QMessageBox.warning(self, "Warnings", "\n".join(errors))
        else: QMessageBox.information(self, "Success", "Settings Applied.")
        self.update_fps_estimate()
        

    def fast_grab(self):
        if not self.cam or self.is_live: return
        try:
            self.target_frames = int(self.frames_input.text())
            w, h = self.cam.get_feature_by_name("Width").get(), self.cam.get_feature_by_name("Height").get()
            fmt = str(self.cam.get_feature_by_name("PixelFormat").get())
            dtype = np.uint8 if "8" in fmt else np.uint16
            self.ram_stack = np.empty((self.target_frames, h, w), dtype=dtype)
            self.frames_acquired = 0
            self.progress_bar.setMaximum(self.target_frames)
            self.cam.start_streaming(handler=self.async_handler, buffer_count=20)
            while self.frames_acquired < self.target_frames:
                self.progress_bar.setValue(self.frames_acquired)
                QApplication.processEvents()
                time.sleep(0.01)
            self.cam.stop_streaming()
            if self.frames_acquired > 0:
                self.ax_first.imshow(self.ram_stack[0], cmap='inferno')
                self.ax_last.imshow(self.ram_stack[self.frames_acquired - 1], cmap='inferno')
            self.save_btn.setEnabled(True)
            self.update_plot(self.ram_stack[0])
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def grab_single(self):
        if not self.cam or self.is_live: return
        try:
            frame = self.cam.get_frame()
            if frame.get_status() == FrameStatus.Complete:
                img_array = frame.as_numpy_ndarray().copy().squeeze()
                
                img_min = int(np.min(img_array))
                img_max = int(np.max(img_array))
                
                if img_min >= img_max:
                    img_max = img_min + 1
                
                self.vmin_slider.blockSignals(True)
                self.vmax_slider.blockSignals(True)
                
                self.vmin_slider.setValue(img_min)
                self.vmax_slider.setValue(img_max)
                
                self.vmin_slider.blockSignals(False)
                self.vmax_slider.blockSignals(False)
                
                self.update_plot(img_array)
        except Exception as e: QMessageBox.critical(self, "Error", str(e))
        
    def update_fps_estimate(self):
        if not self.cam:
            return
            
        try:
            actual_fmt = str(self.cam.get_feature_by_name("PixelFormat").get())
            bytes_per_pixel = 1 if "8" in actual_fmt else 2
            
            actual_w = self.cam.get_feature_by_name("Width").get()
            actual_h = self.cam.get_feature_by_name("Height").get()
            
            frame_size_bytes = actual_w * actual_h * bytes_per_pixel
            
            bandwidth_limit_fps = 380_000_000 / frame_size_bytes if frame_size_bytes > 0 else 999
            
            try:
                exposure_ms = float(self.exp_input.text())
                exposure_limit_fps = 1000.0 / exposure_ms if exposure_ms > 0 else 999
            except ValueError:
                exposure_limit_fps = 999
            
            est_fps = min(bandwidth_limit_fps, exposure_limit_fps)
            self.fps_label.setText(f"Estimated Max FPS: {est_fps:.1f}")
            
        except Exception:
            self.fps_label.setText("Estimated Max FPS: Error calculating")
            
    def save_stack(self):
        if self.ram_stack is None or self.frames_acquired == 0:
            QMessageBox.warning(self, "No Data", "There are no frames in RAM to save.")
            return

        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save RAM Stack as TIFF", 
            "", 
            "TIFF Files (*.tiff *.tif);;All Files (*)", 
            options=options
        )

        if not file_path:
            return

        if not (file_path.lower().endswith('.tif') or file_path.lower().endswith('.tiff')):
            file_path += '.tiff'

        try:
            self.save_btn.setEnabled(False)
            self.save_btn.setText("Saving...")
            QApplication.processEvents() 

            stack_to_save = self.ram_stack[:self.frames_acquired]
            tifffile.imwrite(file_path, stack_to_save, photometric='minisblack')

            QMessageBox.information(
                self, 
                "Success", 
                f"Successfully saved {self.frames_acquired} frames to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Error Saving File", str(e))
            
        finally:
            self.save_btn.setText("Save RAM Stack")
            self.save_btn.setEnabled(True)

    def closeEvent(self, event):
        self.is_live = False
        if self.cam:
            try:
                if self.cam.is_streaming():
                    self.cam.stop_streaming()
                self.cam.__exit__(None, None, None)
            except: pass
        try:
            self.vmb.__exit__(None, None, None)
        except: pass
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = CameraGUI()
    window.show()
    sys.exit(app.exec_())

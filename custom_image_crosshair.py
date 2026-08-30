import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QImage, QPen
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QSlider, QScrollArea, QMessageBox,
    QFrame, QSizePolicy
)

CONFIG_FILE = "crosshair_qt_config.json"


class ZoomableImageLabel(QLabel):
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setStyleSheet("background:#202020;")
        self.setCursor(Qt.CrossCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.parent_app.original_image is None:
            return

        zoom = self.parent_app.preview_zoom
        original_x = event.position().x() / zoom
        original_y = event.position().y() / zoom

        img = self.parent_app.original_image
        if not (0 <= original_x < img.width() and 0 <= original_y < img.height()):
            return

        self.parent_app.mid_x = float(original_x)
        self.parent_app.mid_y = float(original_y)

        self.parent_app.update_preview()
        self.parent_app.update_status()
        self.parent_app.save_config()
        self.parent_app.refresh_overlay()


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.pixmap = None
        self.opacity_value = 1.0

    def set_overlay_pixmap(self, pixmap, opacity):
        self.pixmap = pixmap
        self.opacity_value = opacity
        self.resize(pixmap.size())
        self.update()

    def paintEvent(self, event):
        if self.pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(self.opacity_value)
        painter.drawPixmap(0, 0, self.pixmap)


class CalibrationWindow(QWidget):
    def __init__(self, parent_app):
        super().__init__(None)
        self.parent_app = parent_app
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet("background: rgba(0,0,0,170);")
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        p = event.globalPosition()
        self.parent_app.screen_x = int(p.x())
        self.parent_app.screen_y = int(p.y())
        self.close()
        self.parent_app.update_status()
        self.parent_app.save_config()
        self.parent_app.show_overlay()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()


class CrosshairApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Custom Image Crosshair - Pixel Zoom")
        self.resize(820, 900)
        self.setMinimumSize(650, 600)

        self.image_path = None
        self.original_image = None
        self.mid_x = None
        self.mid_y = None
        self.screen_x = None
        self.screen_y = None

        self.scale_value = 1.0
        self.opacity_value = 1.0
        self.preview_zoom = 0.5

        self.overlay = OverlayWindow()
        self.calibration_window = None

        self.load_config()
        self.build_ui()

        if self.image_path and os.path.exists(self.image_path):
            self.load_image(self.image_path)

    def build_ui(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 30)
        layout.setSpacing(12)

        title = QLabel("Custom Image Crosshair — Pixel Zoom Calibration")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:24px; font-weight:700;")
        layout.addWidget(title)

        info = QLabel(
            "Load an image, zoom in until individual pixels are visible, then click the exact point.\n"
            "The preview zoom is only for calibration and does not change the final overlay size."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        choose = QPushButton("Choose Crosshair Image")
        choose.setMinimumHeight(42)
        choose.clicked.connect(self.choose_image)
        layout.addWidget(choose)

        zoom_title = QLabel("Calibration Zoom")
        zoom_title.setStyleSheet("font-size:15px; font-weight:700;")
        layout.addWidget(zoom_title)

        zoom_row = QHBoxLayout()

        zoom_out = QPushButton("−")
        zoom_out.setFixedWidth(48)
        zoom_out.clicked.connect(self.zoom_out)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 1600)
        self.zoom_slider.setValue(int(self.preview_zoom * 100))
        self.zoom_slider.valueChanged.connect(self.preview_zoom_changed)

        zoom_in = QPushButton("+")
        zoom_in.setFixedWidth(48)
        zoom_in.clicked.connect(self.zoom_in)

        self.zoom_label = QLabel(f"{self.preview_zoom * 100:.0f}%")
        self.zoom_label.setMinimumWidth(70)

        zoom_row.addWidget(zoom_out)
        zoom_row.addWidget(self.zoom_slider)
        zoom_row.addWidget(zoom_in)
        zoom_row.addWidget(self.zoom_label)
        layout.addLayout(zoom_row)

        preset_row = QHBoxLayout()
        presets = [("Fit", None), ("100%", 1.0), ("200%", 2.0), ("400%", 4.0), ("800%", 8.0), ("1600%", 16.0)]
        for label, value in presets:
            btn = QPushButton(label)
            if value is None:
                btn.clicked.connect(self.fit_preview)
            else:
                btn.clicked.connect(lambda checked=False, z=value: self.set_preview_zoom(z))
            preset_row.addWidget(btn)
        layout.addLayout(preset_row)

        help_label = QLabel(
            "At 1600%, each source pixel becomes a 16×16 block. "
            "Use the horizontal and vertical scrollbars to move around the enlarged image."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color:#555;")
        layout.addWidget(help_label)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setMinimumHeight(400)
        self.preview_scroll.setStyleSheet("QScrollArea { background:#202020; border:1px solid #666; }")

        self.preview = ZoomableImageLabel(self)
        self.preview_scroll.setWidget(self.preview)
        layout.addWidget(self.preview_scroll)

        self.pixel_status = QLabel("Click the image to select the exact calibration point.")
        self.pixel_status.setStyleSheet("font-weight:600;")
        self.pixel_status.setWordWrap(True)
        layout.addWidget(self.pixel_status)

        self.status = QLabel("Load an image to begin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        final_title = QLabel("Final Overlay Scale")
        final_title.setStyleSheet("font-weight:700;")
        layout.addWidget(final_title)

        scale_row = QHBoxLayout()
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(5, 300)
        self.scale_slider.setValue(int(self.scale_value * 100))
        self.scale_slider.valueChanged.connect(self.scale_changed)

        self.scale_label = QLabel(f"{self.scale_value:.2f}×")
        self.scale_label.setMinimumWidth(60)

        scale_row.addWidget(self.scale_slider)
        scale_row.addWidget(self.scale_label)
        layout.addLayout(scale_row)

        pixel_btn = QPushButton("Pixel-Perfect Final Overlay 1:1")
        pixel_btn.clicked.connect(self.pixel_perfect)
        layout.addWidget(pixel_btn)

        opacity_title = QLabel("Opacity")
        opacity_title.setStyleSheet("font-weight:700;")
        layout.addWidget(opacity_title)

        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(self.opacity_value * 100))
        self.opacity_slider.valueChanged.connect(self.opacity_changed)

        self.opacity_label = QLabel(f"{self.opacity_value:.2f}")
        self.opacity_label.setMinimumWidth(60)

        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        layout.addLayout(opacity_row)

        pos_row = QHBoxLayout()
        center_btn = QPushButton("Center on Screen")
        center_btn.setMinimumHeight(42)
        center_btn.clicked.connect(self.center_on_screen)

        manual_btn = QPushButton("Manual Calibration")
        manual_btn.setMinimumHeight(42)
        manual_btn.clicked.connect(self.manual_calibration)

        pos_row.addWidget(center_btn)
        pos_row.addWidget(manual_btn)
        layout.addLayout(pos_row)

        overlay_row = QHBoxLayout()
        show_btn = QPushButton("Show Overlay")
        show_btn.setMinimumHeight(42)
        show_btn.clicked.connect(self.show_overlay)

        hide_btn = QPushButton("Hide Overlay")
        hide_btn.setMinimumHeight(42)
        hide_btn.clicked.connect(self.overlay.hide)

        overlay_row.addWidget(show_btn)
        overlay_row.addWidget(hide_btn)
        layout.addLayout(overlay_row)

        layout.addStretch()
        outer.setWidget(body)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(outer)

        self.update_status()

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Crosshair Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return

        self.image_path = path
        self.mid_x = None
        self.mid_y = None
        self.load_image(path)
        self.save_config()

    def load_image(self, path):
        image = QImage(path)
        if image.isNull():
            QMessageBox.critical(self, "Error", "Could not load the selected image.")
            return

        self.original_image = image.convertToFormat(QImage.Format_ARGB32)
        self.fit_preview()
        self.update_preview()
        self.update_status()

    def set_preview_zoom(self, zoom):
        zoom = max(0.10, min(16.0, float(zoom)))
        self.preview_zoom = zoom

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(round(zoom * 100))
        self.zoom_slider.blockSignals(False)

        self.zoom_label.setText(f"{zoom * 100:.0f}%")
        self.update_preview()

    def preview_zoom_changed(self, value):
        self.preview_zoom = value / 100.0
        self.zoom_label.setText(f"{value}%")
        self.update_preview()

    def zoom_in(self):
        self.set_preview_zoom(self.preview_zoom * 1.25)

    def zoom_out(self):
        self.set_preview_zoom(self.preview_zoom / 1.25)

    def fit_preview(self):
        if self.original_image is None:
            return

        viewport = self.preview_scroll.viewport().size()
        available_w = max(100, viewport.width() - 12)
        available_h = max(100, viewport.height() - 12)

        fit_zoom = min(
            available_w / self.original_image.width(),
            available_h / self.original_image.height(),
            1.0
        )
        self.set_preview_zoom(max(0.10, fit_zoom))

    def update_preview(self):
        if self.original_image is None:
            return

        zoom = self.preview_zoom
        w = max(1, round(self.original_image.width() * zoom))
        h = max(1, round(self.original_image.height() * zoom))

        source = QPixmap.fromImage(self.original_image)

        # Nearest-neighbor above 100% so original pixels are easy to inspect.
        mode = Qt.FastTransformation if zoom >= 1.0 else Qt.SmoothTransformation

        displayed = source.scaled(w, h, Qt.IgnoreAspectRatio, mode)

        if self.mid_x is not None and self.mid_y is not None:
            marked = QPixmap(displayed)
            painter = QPainter(marked)
            painter.setRenderHint(QPainter.Antialiasing, False)

            x = self.mid_x * zoom
            y = self.mid_y * zoom

            pen = QPen(Qt.red)
            pen.setWidth(2)
            painter.setPen(pen)

            # At 400%+, draw a box around the exact selected source pixel.
            if zoom >= 4.0:
                px = int(self.mid_x)
                py = int(self.mid_y)
                painter.drawRect(
                    round(px * zoom),
                    round(py * zoom),
                    max(1, round(zoom)),
                    max(1, round(zoom))
                )

            cross = 14
            painter.drawLine(round(x - cross), round(y), round(x + cross), round(y))
            painter.drawLine(round(x), round(y - cross), round(x), round(y + cross))
            painter.end()
            displayed = marked

        self.preview.setPixmap(displayed)
        self.preview.setFixedSize(w, h)
        self.update_pixel_status()

    def update_pixel_status(self):
        if not hasattr(self, "pixel_status"):
            return

        if self.original_image is None:
            self.pixel_status.setText("No image loaded.")
            return

        if self.mid_x is None or self.mid_y is None:
            self.pixel_status.setText(
                f"Zoom: {self.preview_zoom * 100:.0f}% — click the image to select a point."
            )
            return

        px = max(0, min(self.original_image.width() - 1, int(self.mid_x)))
        py = max(0, min(self.original_image.height() - 1, int(self.mid_y)))

        self.pixel_status.setText(
            f"Selected source pixel: X={px}, Y={py}   |   "
            f"Precise point: ({self.mid_x:.3f}, {self.mid_y:.3f})   |   "
            f"Zoom: {self.preview_zoom * 100:.0f}%"
        )

    def scale_changed(self, value):
        self.scale_value = value / 100.0
        self.scale_label.setText(f"{self.scale_value:.2f}×")
        self.refresh_overlay()
        self.save_config()

    def opacity_changed(self, value):
        self.opacity_value = value / 100.0
        self.opacity_label.setText(f"{self.opacity_value:.2f}")
        self.refresh_overlay()
        self.save_config()

    def pixel_perfect(self):
        self.scale_slider.setValue(100)

    def center_on_screen(self):
        if not self.ready():
            return

        screen = QApplication.primaryScreen().geometry()
        self.screen_x = screen.x() + screen.width() // 2
        self.screen_y = screen.y() + screen.height() // 2

        self.update_status()
        self.save_config()
        self.show_overlay()

    def manual_calibration(self):
        if not self.ready():
            return

        self.overlay.hide()
        self.calibration_window = CalibrationWindow(self)
        self.calibration_window.showFullScreen()
        self.calibration_window.activateWindow()

    def ready(self):
        if self.original_image is None:
            QMessageBox.information(self, "No image", "Choose an image first.")
            return False

        if self.mid_x is None or self.mid_y is None:
            QMessageBox.information(
                self,
                "Set midpoint",
                "Zoom into the image and click the desired aiming point first."
            )
            return False

        return True

    def show_overlay(self):
        if not self.ready():
            return

        if self.screen_x is None or self.screen_y is None:
            screen = QApplication.primaryScreen().geometry()
            self.screen_x = screen.x() + screen.width() // 2
            self.screen_y = screen.y() + screen.height() // 2

        self.refresh_overlay()
        self.overlay.show()
        self.overlay.raise_()

    def refresh_overlay(self):
        if (
            self.original_image is None
            or self.mid_x is None
            or self.mid_y is None
            or self.screen_x is None
            or self.screen_y is None
        ):
            return

        scale = self.scale_value

        if abs(scale - 1.0) < 1e-9:
            pixmap = QPixmap.fromImage(self.original_image)
        else:
            w = max(1, round(self.original_image.width() * scale))
            h = max(1, round(self.original_image.height() * scale))
            pixmap = QPixmap.fromImage(self.original_image).scaled(
                w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )

        self.overlay.set_overlay_pixmap(pixmap, self.opacity_value)
        self.overlay.move(
            round(self.screen_x - self.mid_x * scale),
            round(self.screen_y - self.mid_y * scale)
        )

    def update_status(self):
        name = os.path.basename(self.image_path) if self.image_path else "None"
        point = (
            f"({self.mid_x:.3f}, {self.mid_y:.3f})"
            if self.mid_x is not None
            else "Not selected"
        )
        target = (
            f"({self.screen_x}, {self.screen_y})"
            if self.screen_x is not None
            else "Not calibrated"
        )

        if hasattr(self, "status"):
            self.status.setText(
                f"Image: {name}\nCalibration point: {point}\nScreen target: {target}"
            )

        self.update_pixel_status()

    def save_config(self):
        data = {
            "image_path": self.image_path,
            "mid_x": self.mid_x,
            "mid_y": self.mid_y,
            "screen_x": self.screen_x,
            "screen_y": self.screen_y,
            "scale": self.scale_value,
            "opacity": self.opacity_value,
            "preview_zoom": self.preview_zoom,
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.image_path = data.get("image_path")
            self.mid_x = data.get("mid_x")
            self.mid_y = data.get("mid_y")
            self.screen_x = data.get("screen_x")
            self.screen_y = data.get("screen_y")
            self.scale_value = float(data.get("scale", 1.0))
            self.opacity_value = float(data.get("opacity", 1.0))
            self.preview_zoom = max(
                0.10,
                min(16.0, float(data.get("preview_zoom", 0.5)))
            )
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_config()
        self.overlay.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = CrosshairApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

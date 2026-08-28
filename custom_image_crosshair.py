import json
import os
import sys

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPixmap, QPainter, QImage
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QSlider, QScrollArea, QMessageBox,
    QFrame
)

CONFIG_FILE = "crosshair_qt_config.json"


class ImagePickerLabel(QLabel):
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.setFixedSize(520, 360)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#202020; border:1px solid #666;")
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self.parent_app.original_image is None:
            return

        pixmap = self.pixmap()
        if pixmap is None:
            return

        # Displayed pixmap is centered in this QLabel.
        px = int((self.width() - pixmap.width()) / 2)
        py = int((self.height() - pixmap.height()) / 2)

        local_x = event.position().x() - px
        local_y = event.position().y() - py

        if not (0 <= local_x < pixmap.width() and 0 <= local_y < pixmap.height()):
            return

        original = self.parent_app.original_image

        scale_x = original.width() / pixmap.width()
        scale_y = original.height() / pixmap.height()

        self.parent_app.mid_x = local_x * scale_x
        self.parent_app.mid_y = local_y * scale_y

        self.parent_app.update_preview()
        self.parent_app.update_status()
        self.parent_app.save_config()
        self.parent_app.refresh_overlay()


class CalibrationWindow(QWidget):
    def __init__(self, parent_app):
        super().__init__(None)
        self.parent_app = parent_app

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())

        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        painter.setOpacity(0.65)
        painter.setPen(Qt.white)

    def mousePressEvent(self, event):
        global_pos = event.globalPosition()

        self.parent_app.screen_x = int(global_pos.x())
        self.parent_app.screen_y = int(global_pos.y())

        self.close()
        self.parent_app.update_status()
        self.parent_app.save_config()
        self.parent_app.show_overlay()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()


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

        # High quality composition with true per-pixel alpha.
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(self.opacity_value)
        painter.drawPixmap(0, 0, self.pixmap)


class CrosshairApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Custom Image Crosshair - HQ Qt")
        self.resize(760, 820)
        self.setMinimumSize(600, 540)

        self.image_path = None
        self.original_image = None

        self.mid_x = None
        self.mid_y = None

        self.screen_x = None
        self.screen_y = None

        self.scale_value = 1.0
        self.opacity_value = 1.0

        self.overlay = OverlayWindow()
        self.calibration_window = None

        self.load_config()
        self.build_ui()

        if self.image_path and os.path.exists(self.image_path):
            self.load_image(self.image_path)

    def build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 30)
        layout.setSpacing(12)

        title = QLabel("Custom Image Crosshair — HQ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:24px; font-weight:700;")
        layout.addWidget(title)

        info = QLabel(
            "1. Load a PNG/image\n"
            "2. Click the exact aiming point inside the image\n"
            "3. Press Center on Screen\n"
            "4. Show the overlay\n\n"
            "This version uses real per-pixel transparency instead of color-key transparency."
        )
        info.setStyleSheet("font-size:13px;")
        layout.addWidget(info)

        choose = QPushButton("Choose Crosshair Image")
        choose.setMinimumHeight(42)
        choose.clicked.connect(self.choose_image)
        layout.addWidget(choose)

        self.preview = ImagePickerLabel(self)
        layout.addWidget(self.preview, alignment=Qt.AlignCenter)

        self.status = QLabel("Load an image to begin.")
        self.status.setStyleSheet("font-size:13px;")
        layout.addWidget(self.status)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        scale_text = QLabel("Overlay scale")
        scale_text.setStyleSheet("font-weight:600;")
        layout.addWidget(scale_text)

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

        pixel_btn = QPushButton("Pixel-Perfect 1:1")
        pixel_btn.clicked.connect(self.pixel_perfect)
        layout.addWidget(pixel_btn)

        quality_note = QLabel(
            "1.00× = exact source pixels, with no resizing.\n"
            "Below 1.00× = image is downscaled, but Qt uses high-quality filtering."
        )
        quality_note.setStyleSheet("color:#666;")
        layout.addWidget(quality_note)

        opacity_text = QLabel("Opacity")
        opacity_text.setStyleSheet("font-weight:600;")
        layout.addWidget(opacity_text)

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

        position_title = QLabel("Screen Position")
        position_title.setStyleSheet("font-size:15px; font-weight:700;")
        layout.addWidget(position_title)

        position_row = QHBoxLayout()

        center_btn = QPushButton("Center on Screen")
        center_btn.setMinimumHeight(42)
        center_btn.clicked.connect(self.center_on_screen)

        manual_btn = QPushButton("Manual Calibration")
        manual_btn.setMinimumHeight(42)
        manual_btn.clicked.connect(self.manual_calibration)

        position_row.addWidget(center_btn)
        position_row.addWidget(manual_btn)
        layout.addLayout(position_row)

        overlay_row = QHBoxLayout()

        show_btn = QPushButton("Show Overlay")
        show_btn.setMinimumHeight(42)
        show_btn.clicked.connect(self.show_overlay)

        hide_btn = QPushButton("Hide Overlay")
        hide_btn.setMinimumHeight(42)
        hide_btn.clicked.connect(self.hide_overlay)

        overlay_row.addWidget(show_btn)
        overlay_row.addWidget(hide_btn)
        layout.addLayout(overlay_row)

        tip = QLabel(
            "Best quality: use a transparent PNG and keep scale at 1.00×.\n"
            "If you want the character smaller without losing edge quality, use a large original PNG."
        )
        tip.setStyleSheet("color:#555;")
        layout.addWidget(tip)

        layout.addStretch()

        scroll.setWidget(body)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

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

        # Preserve the original ARGB pixels, including alpha.
        self.original_image = image.convertToFormat(QImage.Format_ARGB32)

        self.update_preview()
        self.update_status()

    def update_preview(self):
        if self.original_image is None:
            return

        preview_pixmap = QPixmap.fromImage(self.original_image)

        preview_pixmap = preview_pixmap.scaled(
            500,
            340,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        if self.mid_x is not None and self.mid_y is not None:
            marked = QPixmap(preview_pixmap)
            painter = QPainter(marked)
            painter.setRenderHint(QPainter.Antialiasing, True)

            scale_x = preview_pixmap.width() / self.original_image.width()
            scale_y = preview_pixmap.height() / self.original_image.height()

            x = self.mid_x * scale_x
            y = self.mid_y * scale_y

            pen = painter.pen()
            pen.setColor(Qt.red)
            pen.setWidth(2)
            painter.setPen(pen)

            r = 10
            painter.drawEllipse(QPoint(int(x), int(y)), r, r)
            painter.drawLine(int(x - 18), int(y), int(x + 18), int(y))
            painter.drawLine(int(x), int(y - 18), int(x), int(y + 18))
            painter.end()

            preview_pixmap = marked

        self.preview.setPixmap(preview_pixmap)

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
        self.scale_value = 1.0
        self.scale_slider.setValue(100)
        self.refresh_overlay()
        self.save_config()

    def center_on_screen(self):
        if not self.ready_for_position():
            return

        screen = QApplication.primaryScreen().geometry()

        self.screen_x = screen.x() + screen.width() // 2
        self.screen_y = screen.y() + screen.height() // 2

        self.update_status()
        self.save_config()
        self.show_overlay()

    def manual_calibration(self):
        if not self.ready_for_position():
            return

        self.hide_overlay()

        self.calibration_window = CalibrationWindow(self)
        self.calibration_window.showFullScreen()
        self.calibration_window.activateWindow()

    def ready_for_position(self):
        if self.original_image is None:
            QMessageBox.information(self, "No image", "Choose an image first.")
            return False

        if self.mid_x is None or self.mid_y is None:
            QMessageBox.information(
                self,
                "Set midpoint",
                "Click the desired aiming point inside the image first."
            )
            return False

        return True

    def show_overlay(self):
        if not self.ready_for_position():
            return

        if self.screen_x is None or self.screen_y is None:
            screen = QApplication.primaryScreen().geometry()
            self.screen_x = screen.x() + screen.width() // 2
            self.screen_y = screen.y() + screen.height() // 2

        self.refresh_overlay()
        self.overlay.show()
        self.overlay.raise_()

    def hide_overlay(self):
        self.overlay.hide()

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

        # At exactly 1.0, do not rescale at all.
        if abs(scale - 1.0) < 1e-9:
            pixmap = QPixmap.fromImage(self.original_image)
            new_w = self.original_image.width()
            new_h = self.original_image.height()
        else:
            new_w = max(1, round(self.original_image.width() * scale))
            new_h = max(1, round(self.original_image.height() * scale))

            pixmap = QPixmap.fromImage(self.original_image).scaled(
                new_w,
                new_h,
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation
            )

        self.overlay.set_overlay_pixmap(pixmap, self.opacity_value)

        mid_scaled_x = self.mid_x * scale
        mid_scaled_y = self.mid_y * scale

        x = round(self.screen_x - mid_scaled_x)
        y = round(self.screen_y - mid_scaled_y)

        self.overlay.move(x, y)

    def update_status(self):
        image_name = os.path.basename(self.image_path) if self.image_path else "None"

        if self.mid_x is None:
            midpoint = "Not selected"
        else:
            midpoint = f"({self.mid_x:.1f}, {self.mid_y:.1f})"

        if self.screen_x is None:
            target = "Not calibrated"
        else:
            target = f"({self.screen_x}, {self.screen_y})"

        if hasattr(self, "status"):
            self.status.setText(
                f"Image: {image_name}\n"
                f"Image midpoint: {midpoint}\n"
                f"Screen target: {target}"
            )

    def save_config(self):
        data = {
            "image_path": self.image_path,
            "mid_x": self.mid_x,
            "mid_y": self.mid_y,
            "screen_x": self.screen_x,
            "screen_y": self.screen_y,
            "scale": self.scale_value,
            "opacity": self.opacity_value
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

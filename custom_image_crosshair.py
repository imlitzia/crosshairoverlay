import json, os, sys, tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

CONFIG_FILE = "crosshair_config.json"

class CrosshairApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Custom Image Crosshair")
        self.root.geometry("650x760")
        self.root.minsize(520, 500)
        self.root.resizable(True, True)

        self.image_path = None
        self.original_image = None
        self.preview_image = None
        self.preview_photo = None
        self.mid_x = self.mid_y = None
        self.screen_x = self.screen_y = None
        self.overlay = None
        self.overlay_photo = None
        self.scale = tk.DoubleVar(value=0.25)
        self.opacity = tk.DoubleVar(value=1.0)

        self.load_config()
        self.build_ui()
        if self.image_path and os.path.exists(self.image_path):
            try:
                self.load_image(self.image_path)
            except Exception:
                pass
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        outer = tk.Frame(self.root)
        outer.pack(fill="both", expand=True)

        self.scroll_canvas = tk.Canvas(outer, highlightthickness=0)
        bar = tk.Scrollbar(outer, orient="vertical", command=self.scroll_canvas.yview)
        self.scroll_canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.scroll_canvas.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(self.scroll_canvas)
        self.content_id = self.scroll_canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")))
        self.scroll_canvas.bind("<Configure>", lambda e: self.scroll_canvas.itemconfigure(self.content_id, width=e.width))
        self.root.bind_all("<MouseWheel>", self.mousewheel)

        tk.Label(self.content, text="Custom Image Crosshair", font=("Segoe UI", 20, "bold")).pack(pady=(18, 8))
        tk.Label(self.content, justify="left", font=("Segoe UI", 10), text=(
            "1. Load an image\n"
            "2. Click the point inside the image that should be the crosshair center\n"
            "3. Press Center on Screen for an exact monitor-center target\n"
            "4. Show the overlay"
        )).pack(padx=25, pady=8, anchor="w")

        tk.Button(self.content, text="Choose Crosshair Image", command=self.choose_image, width=30, height=2).pack(pady=10)

        self.image_canvas = tk.Canvas(self.content, width=440, height=320, bg="#222222", highlightthickness=1,
                                      highlightbackground="#666666", cursor="crosshair")
        self.image_canvas.pack(pady=10)
        self.image_canvas.bind("<Button-1>", self.set_image_midpoint)

        self.status = tk.Label(self.content, text="Load an image to begin.", font=("Segoe UI", 10),
                               wraplength=560, justify="left")
        self.status.pack(padx=25, pady=8, anchor="w")

        controls = tk.Frame(self.content)
        controls.pack(fill="x", padx=25, pady=8)
        tk.Label(controls, text="Overlay scale:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        tk.Scale(controls, from_=0.05, to=3.0, resolution=0.05, orient="horizontal", variable=self.scale,
                 command=lambda _: self.refresh_overlay()).grid(row=0, column=1, sticky="ew")
        tk.Label(controls, text="Opacity:").grid(row=1, column=0, sticky="w", padx=(0, 10))
        tk.Scale(controls, from_=0.1, to=1.0, resolution=0.05, orient="horizontal", variable=self.opacity,
                 command=lambda _: self.refresh_overlay()).grid(row=1, column=1, sticky="ew")
        controls.columnconfigure(1, weight=1)

        tk.Label(self.content, text="Screen Position", font=("Segoe UI", 12, "bold")).pack(pady=(15, 6))
        pos = tk.Frame(self.content); pos.pack(pady=5)
        tk.Button(pos, text="Center on Screen", command=self.center_on_screen, width=22, height=2).grid(row=0, column=0, padx=6)
        tk.Button(pos, text="Manual Calibration", command=self.manual_calibration, width=22, height=2).grid(row=0, column=1, padx=6)

        buttons = tk.Frame(self.content); buttons.pack(pady=12)
        tk.Button(buttons, text="Show Overlay", command=self.show_overlay, width=20, height=2).grid(row=0, column=0, padx=6)
        tk.Button(buttons, text="Hide Overlay", command=self.hide_overlay, width=20, height=2).grid(row=0, column=1, padx=6)

        tk.Label(self.content, fg="#555555", font=("Segoe UI", 9), justify="center",
                 text="Normal FPS use: select the aiming point inside the image, then press Center on Screen.").pack(pady=(8, 3))
        tk.Label(self.content, fg="#666666", font=("Segoe UI", 9),
                 text="PNG images with transparent backgrounds work best.").pack(pady=(0, 25))

    def mousewheel(self, event):
        self.scroll_canvas.yview_scroll(int(-event.delta / 120), "units")

    def choose_image(self):
        path = filedialog.askopenfilename(title="Choose crosshair image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")])
        if not path: return
        self.image_path = path
        self.mid_x = self.mid_y = None
        self.load_image(path)
        self.save_config()

    def load_image(self, path):
        self.original_image = Image.open(path).convert("RGBA")
        self.preview_image = self.original_image.copy()
        self.preview_image.thumbnail((420, 300), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(self.preview_image)
        self.image_canvas.delete("all")
        self.preview_left = (440 - self.preview_image.width) // 2
        self.preview_top = (320 - self.preview_image.height) // 2
        self.image_canvas.create_image(self.preview_left, self.preview_top, anchor="nw", image=self.preview_photo)
        if self.mid_x is not None: self.draw_midpoint()
        self.update_status()

    def set_image_midpoint(self, event):
        if self.original_image is None:
            messagebox.showinfo("No image", "Choose an image first."); return
        px, py = event.x - self.preview_left, event.y - self.preview_top
        if not (0 <= px < self.preview_image.width and 0 <= py < self.preview_image.height): return
        self.mid_x = px * self.original_image.width / self.preview_image.width
        self.mid_y = py * self.original_image.height / self.preview_image.height
        self.draw_midpoint(); self.update_status(); self.save_config(); self.refresh_overlay()

    def draw_midpoint(self):
        self.image_canvas.delete("midpoint")
        x = self.preview_left + self.mid_x * self.preview_image.width / self.original_image.width
        y = self.preview_top + self.mid_y * self.preview_image.height / self.original_image.height
        r = 9
        self.image_canvas.create_oval(x-r, y-r, x+r, y+r, outline="#ff3333", width=2, tags="midpoint")
        self.image_canvas.create_line(x-r-7, y, x+r+7, y, fill="#ff3333", width=2, tags="midpoint")
        self.image_canvas.create_line(x, y-r-7, x, y+r+7, fill="#ff3333", width=2, tags="midpoint")

    def validate_ready(self):
        if self.original_image is None:
            messagebox.showinfo("No image", "Choose an image first."); return False
        if self.mid_x is None:
            messagebox.showinfo("Set midpoint", "Click the desired aiming point inside the image first."); return False
        return True

    def center_on_screen(self):
        if not self.validate_ready(): return
        # Exact center of the primary display.
        self.root.update_idletasks()
        self.screen_x = self.root.winfo_screenwidth() // 2
        self.screen_y = self.root.winfo_screenheight() // 2
        self.update_status(); self.save_config(); self.show_overlay()

    def manual_calibration(self):
        if not self.validate_ready(): return
        self.hide_overlay()
        cal = tk.Toplevel(self.root)
        cal.attributes("-fullscreen", True); cal.attributes("-topmost", True); cal.attributes("-alpha", 0.30)
        cal.configure(bg="black", cursor="crosshair")
        tk.Label(cal, text="CLICK where the selected image midpoint should appear\n\nPress ESC to cancel",
                 bg="black", fg="white", font=("Segoe UI", 18, "bold")).place(relx=.5, rely=.12, anchor="center")
        def clicked(e):
            self.screen_x, self.screen_y = e.x_root, e.y_root
            cal.destroy(); self.update_status(); self.save_config(); self.show_overlay()
        cal.bind("<Button-1>", clicked); cal.bind("<Escape>", lambda e: cal.destroy()); cal.focus_force()

    def show_overlay(self):
        if not self.validate_ready(): return
        if self.screen_x is None:
            self.screen_x = self.root.winfo_screenwidth() // 2
            self.screen_y = self.root.winfo_screenheight() // 2
        if self.overlay is None or not self.overlay.winfo_exists():
            self.overlay = tk.Toplevel(self.root)
            self.overlay.overrideredirect(True); self.overlay.attributes("-topmost", True)
            self.transparent_color = "#010101"
            self.overlay.configure(bg=self.transparent_color)
            try: self.overlay.wm_attributes("-transparentcolor", self.transparent_color)
            except tk.TclError: pass
            self.overlay_label = tk.Label(self.overlay, bg=self.transparent_color, borderwidth=0, highlightthickness=0)
            self.overlay_label.pack()
        self.refresh_overlay(); self.overlay.deiconify(); self.make_click_through()

    def refresh_overlay(self):
        if not (self.overlay and self.overlay.winfo_exists() and self.original_image and self.mid_x is not None and self.screen_x is not None): return
        s = self.scale.get()
        w, h = max(1, int(self.original_image.width*s)), max(1, int(self.original_image.height*s))
        img = self.original_image.resize((w, h), Image.Resampling.LANCZOS)
        self.overlay_photo = ImageTk.PhotoImage(img)
        self.overlay_label.configure(image=self.overlay_photo)
        x = int(self.screen_x - self.mid_x*s)
        y = int(self.screen_y - self.mid_y*s)
        self.overlay.geometry(f"{w}x{h}+{x}+{y}")
        try: self.overlay.attributes("-alpha", self.opacity.get())
        except tk.TclError: pass
        self.overlay.lift(); self.make_click_through()

    def make_click_through(self):
        if sys.platform != "win32" or not self.overlay: return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.overlay.winfo_id())
            GWL_EXSTYLE=-20; WS_EX_LAYERED=0x00080000; WS_EX_TRANSPARENT=0x20; WS_EX_TOOLWINDOW=0x80; WS_EX_NOACTIVATE=0x08000000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style|WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0,0,0,0, 0x0002|0x0001|0x0010)
        except Exception: pass

    def hide_overlay(self):
        if self.overlay and self.overlay.winfo_exists(): self.overlay.withdraw()

    def update_status(self):
        img = os.path.basename(self.image_path) if self.image_path else "None"
        mid = f"({self.mid_x:.1f}, {self.mid_y:.1f})" if self.mid_x is not None else "Not selected"
        target = f"({self.screen_x}, {self.screen_y})" if self.screen_x is not None else "Not calibrated"
        self.status.configure(text=f"Image: {img}\nImage midpoint: {mid}\nScreen target: {target}")

    def save_config(self):
        data = {"image_path": self.image_path, "mid_x": self.mid_x, "mid_y": self.mid_y,
                "screen_x": self.screen_x, "screen_y": self.screen_y,
                "scale": self.scale.get(), "opacity": self.opacity.get()}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
        except Exception: pass

    def load_config(self):
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f: d=json.load(f)
            self.image_path=d.get("image_path"); self.mid_x=d.get("mid_x"); self.mid_y=d.get("mid_y")
            self.screen_x=d.get("screen_x"); self.screen_y=d.get("screen_y")
            if "scale" in d: self.scale.set(d["scale"])
            if "opacity" in d: self.opacity.set(d["opacity"])
        except Exception: pass

    def on_close(self):
        self.save_config(); self.root.destroy()

    def run(self): self.root.mainloop()

if __name__ == "__main__":
    CrosshairApp().run()
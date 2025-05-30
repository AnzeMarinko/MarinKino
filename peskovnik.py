from priprava_filmov.realesrgan import upscale_image, upscale_video
import cv2
import os
import tkinter as tk
from PIL import Image, ImageTk
import time

# Nastavitve modelov
available_models = {
    "original": None,
    "GAN x2": "RealESRGAN_x2plus",
    "GAN x4": "RealESRGAN_x4plus",
    "Net x4": "RealESRNet_x4plus",
    "anime x4": "realesr-animevideov3",
    "GAN anime x4": "RealESRGAN_x4plus_anime_6B",
}

class VideoSwitcherApp:
    def __init__(self, master, videos):
        self.master = master
        self.master.title("Video primerjava")

        # Video viri
        self.cap_videos = videos
        self.current_cap = self.cap_videos["original"]
        self.video_names = list(videos.keys())
        self.switch = 0
        self.paused = False

        # Informacije o videu
        self.total_frames = int(self.current_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.current_cap.get(cv2.CAP_PROP_FPS)
        self.width = 1920
        self.height = 1080

        # Platno za video
        self.canvas = tk.Canvas(master, width=self.width, height=self.height)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.toggle_video)

        # Napis (Original/Upscaled)
        self.label = tk.Label(master, text="Original", font=("Arial", 16), bg="black", fg="white")
        self.label.place(x=10, y=10)

        # Kontrolni gumbi
        controls = tk.Frame(master)
        controls.pack(fill=tk.X, pady=5)

        self.play_button = tk.Button(controls, text="⏸ Pavza", width=10, command=self.toggle_play)
        self.play_button.pack(side=tk.LEFT, padx=10)

        self.slider = tk.Scale(
            controls, from_=0, to=self.total_frames - 1, orient=tk.HORIZONTAL,
            length=self.width - 200, command=self.seek_video
        )
        self.slider.pack(side=tk.LEFT)

        self.update_frame()

    def toggle_video(self, event=None):
        current_frame = int(self.current_cap.get(cv2.CAP_PROP_POS_FRAMES))
        self.switch = (self.switch + 1) % len(self.video_names)
        video_name = self.video_names[self.switch]
        self.current_cap = self.cap_videos[video_name]
        self.current_cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        self.label.config(text=video_name)

    def toggle_play(self):
        self.paused = not self.paused
        self.play_button.config(text="▶️ Nadaljuj" if self.paused else "⏸ Pavza")

    def seek_video(self, value):
        frame_num = int(value)
        self.current_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)

    def update_frame(self):
        if not self.paused:
            ret, frame = self.current_cap.read()
            if not ret:
                self.current_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.current_cap.read()

            if ret:
                current_frame = int(self.current_cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.slider.set(current_frame)

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                self.photo = ImageTk.PhotoImage(image=img)
                self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

        delay = int(1000 / self.fps)
        self.master.after(delay, self.update_frame)

def main():
    tk.Tk().withdraw()
    output = {}
    original_video_path = os.path.join("movies", "01-risanke", "Bee.Movie.2007", "Bee.Movie.2007.mp4")
    videos = {"original": original_video_path}
    for m, model_name in available_models.items():
        if model_name:
            print(model_name)
            t = time.time()
            videos[m] = cv2.VideoCapture(upscale_video(original_video_path, model_name, suffix="_" + m.replace(" ", "-")))
            print(model_name, time.time() - t)
            output[model_name] = time.time() - t
    print(output)
    root = tk.Tk()
    app = VideoSwitcherApp(root, videos)
    root.mainloop()


if __name__ == "__main__":
    main()

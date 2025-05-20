import cv2
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import numpy as np
import os


class VideoProcessor:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise ValueError("无法打开视频文件")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_duration = 1 / self.fps
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.current_frame = 0
        self.start_time = 0.0
        self.end_time = self.duration
        self.crop_params = [0, 0, self.width, self.height]
        self.drawing = False
        self.ix, self.iy = -1, -1

    def get_frame(self, time_sec):
        frame_pos = int(round(time_sec * self.fps))
        frame_pos = max(0, min(frame_pos, self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = self.cap.read()
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if ret else None

    def get_cropped_frame(self, frame):
        x, y, w, h = self.crop_params
        return frame[y:y + h, x:x + w]


class VideoEditorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("专业视频编辑器")
        self.setup_ui()
        self.video_processor = None
        self.selection_rect = None
        self.crop_rect = None
        self.ix, self.iy = -1, -1
        self.image_scale = 1.0
        self.tk_img = None

    def setup_ui(self):
        # 控制面板
        control_frame = ttk.Frame(self.root)
        control_frame.pack(pady=5, fill='x')

        # 时间控制组件
        self.setup_time_controls(control_frame)

        # 视频显示区域
        self.setup_video_display()

        # 控制按钮
        self.setup_control_buttons()

    def setup_time_controls(self, parent):
        time_control = ttk.Frame(parent)
        time_control.pack(pady=5)

        # 时间滑动条
        self.time_slider = ttk.Scale(time_control, from_=0, to=1000,
                                     command=lambda v: self.on_slider_move(float(v) / 1000))
        self.time_slider.pack(side=tk.LEFT, fill='x', expand=True, padx=5)

        # 帧导航按钮
        nav_frame = ttk.Frame(time_control)
        nav_frame.pack(side=tk.LEFT)
        ttk.Button(nav_frame, text="←", width=3, command=lambda: self.step_frame(-1)).pack(side=tk.LEFT)
        ttk.Button(nav_frame, text="→", width=3, command=lambda: self.step_frame(1)).pack(side=tk.LEFT)

        # 时间显示标签
        self.time_label = ttk.Label(parent)
        self.time_label.pack()

        # 剪辑范围控制
        self.setup_range_controls(parent)

    def setup_range_controls(self, parent):
        range_control = ttk.Frame(parent)
        range_control.pack(pady=5)

        # 起始点控制
        self.setup_point_control(range_control, "起始点", 'start')
        # 结束点控制
        self.setup_point_control(range_control, "结束点", 'end')

        self.range_label = ttk.Label(parent)
        self.range_label.pack()

    def setup_point_control(self, parent, label_text, point_type):
        frame = ttk.Frame(parent)
        frame.pack(side=tk.LEFT, padx=10)
        ttk.Label(frame, text=f"{label_text}:").pack()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack()
        ttk.Button(btn_frame, text="-1帧",
                   command=lambda: self.adjust_cut_point(point_type, -1)).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="+1帧",
                   command=lambda: self.adjust_cut_point(point_type, 1)).pack(side=tk.LEFT)
        ttk.Button(frame, text="设为当前",
                   command=lambda: self.set_cut_point(point_type)).pack(pady=2)

    def setup_video_display(self):
        self.video_frame = ttk.Frame(self.root)
        self.video_frame.pack(pady=5, expand=True, fill='both')

        # 创建带滚动条的Canvas
        self.canvas = tk.Canvas(self.video_frame, bg='gray')
        self.h_scroll = ttk.Scrollbar(self.video_frame, orient='horizontal', command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(self.video_frame, orient='vertical', command=self.canvas.yview)

        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        self.h_scroll.pack(side='bottom', fill='x')
        self.v_scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', expand=True, fill='both')

        # 绑定鼠标事件
        self.canvas.bind("<Button-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)

    def setup_control_buttons(self):
        self.btn_frame = ttk.Frame(self.root)
        self.btn_frame.pack(pady=5)
        ttk.Button(self.btn_frame, text="导出视频", command=self.export_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.btn_frame, text="导出帧图像", command=self.export_frames).pack(side=tk.LEFT, padx=5)

    # 鼠标事件处理
    def mouse_down(self, event):
        if self.video_processor:
            self.video_processor.drawing = True
            self.ix = self.canvas.canvasx(event.x)
            self.iy = self.canvas.canvasy(event.y)
            self.selection_rect = self.canvas.create_rectangle(
                self.ix, self.iy, self.ix, self.iy, outline='red')

    def mouse_move(self, event):
        if self.video_processor and self.video_processor.drawing:
            x = self.canvas.canvasx(event.x)
            y = self.canvas.canvasy(event.y)
            self.canvas.coords(self.selection_rect, self.ix, self.iy, x, y)

    def mouse_up(self, event):
        if self.video_processor and self.video_processor.drawing:
            self.video_processor.drawing = False
            x = self.canvas.canvasx(event.x)
            y = self.canvas.canvasy(event.y)

            # 转换坐标到原始尺寸
            x1 = min(max(self.ix / self.image_scale, 0), self.video_processor.width)
            y1 = min(max(self.iy / self.image_scale, 0), self.video_processor.height)
            x2 = min(max(x / self.image_scale, 0), self.video_processor.width)
            y2 = min(max(y / self.image_scale, 0), self.video_processor.height)

            self.video_processor.crop_params = [
                int(min(x1, x2)),
                int(min(y1, y2)),
                int(abs(x2 - x1)),
                int(abs(y2 - y1))
            ]
            self.canvas.delete(self.selection_rect)
            self.update_display()

    def load_video(self, path):
        try:
            self.video_processor = VideoProcessor(path)
            self.time_slider.config(to=self.video_processor.duration * 1000)
            self.update_display()
            self.update_range_display()
        except Exception as e:
            messagebox.showerror("错误", f"无法加载视频: {str(e)}")

    def safe_resize(self, img, new_width, new_height):
        """安全调整图像尺寸"""
        new_width = max(1, new_width)
        new_height = max(1, new_height)
        return img.resize((new_width, new_height), Image.LANCZOS)

    def update_display(self):
        if self.video_processor:
            try:
                current_time = self.video_processor.current_frame / self.video_processor.fps
                frame = self.video_processor.get_frame(current_time)

                if frame is None:
                    return

                # 获取有效画布尺寸
                canvas_width = max(1, self.canvas.winfo_width())
                canvas_height = max(1, self.canvas.winfo_height())

                # 计算缩放比例
                h_scale = canvas_width / frame.shape[1]
                v_scale = canvas_height / frame.shape[0]
                self.image_scale = min(h_scale, v_scale, 1)  # 最大保持原始尺寸

                # 计算新尺寸
                new_width = int(frame.shape[1] * self.image_scale)
                new_height = int(frame.shape[0] * self.image_scale)

                # 调整图像尺寸
                img = Image.fromarray(frame)
                img = self.safe_resize(img, new_width, new_height)

                # 更新Canvas
                self.canvas.delete("all")
                self.tk_img = ImageTk.PhotoImage(img)
                self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
                self.canvas.config(scrollregion=(0, 0, new_width, new_height))

                # 绘制裁剪区域
                if sum(self.video_processor.crop_params) > 0:
                    x, y, w, h = self.video_processor.crop_params
                    self.canvas.create_rectangle(
                        x * self.image_scale, y * self.image_scale,
                        (x + w) * self.image_scale, (y + h) * self.image_scale,
                        outline='blue', width=2)

                # 更新时间显示
                self.time_label.config(
                    text=f"当前时间: {current_time:.6f}s | "
                         f"帧号: {self.video_processor.current_frame} | "
                         f"帧率: {self.video_processor.fps:.6f} FPS"
                )
            except Exception as e:
                print(f"显示更新错误: {str(e)}")

    def on_slider_move(self, value):
        if self.video_processor:
            time_sec = value
            frame = round(time_sec * self.video_processor.fps)
            self.video_processor.current_frame = max(0, min(frame, self.video_processor.total_frames - 1))
            self.update_display()

    def step_frame(self, step):
        if self.video_processor:
            new_frame = self.video_processor.current_frame + step
            new_frame = max(0, min(new_frame, self.video_processor.total_frames - 1))
            self.video_processor.current_frame = new_frame
            self.time_slider.set(new_frame / self.video_processor.fps * 1000)
            self.update_display()

    def adjust_cut_point(self, point_type, step):
        if not self.video_processor:
            return

        step_time = step * self.video_processor.frame_duration
        if point_type == 'start':
            new_time = max(0, min(
                self.video_processor.start_time + step_time,
                self.video_processor.end_time - self.video_processor.frame_duration
            ))
            self.video_processor.start_time = round(new_time, 6)
        else:
            new_time = min(self.video_processor.duration, max(
                self.video_processor.end_time + step_time,
                self.video_processor.start_time + self.video_processor.frame_duration
            ))
            self.video_processor.end_time = round(new_time, 6)

        self.update_range_display()

    def set_cut_point(self, point_type):
        if self.video_processor:
            current_time = self.video_processor.current_frame / self.video_processor.fps
            current_time = round(current_time, 6)

            if point_type == 'start':
                self.video_processor.start_time = max(0, min(
                    current_time,
                    self.video_processor.end_time - self.video_processor.frame_duration
                ))
            else:
                self.video_processor.end_time = min(self.video_processor.duration, max(
                    current_time,
                    self.video_processor.start_time + self.video_processor.frame_duration
                ))

            self.update_range_display()

    def update_range_display(self):
        if self.video_processor:
            duration = self.video_processor.end_time - self.video_processor.start_time
            self.range_label.config(
                text=f"剪辑范围: {self.video_processor.start_time:.6f}s - {self.video_processor.end_time:.6f}s\n"
                     f"时长: {duration:.6f}s ({duration / self.video_processor.frame_duration:.2f} 帧)"
            )

    def export_video(self):
        if not self.video_processor:
            return

        output_path = "output.mp4"
        try:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(
                output_path, fourcc, self.video_processor.fps,
                (self.video_processor.crop_params[2],
                 self.video_processor.crop_params[3])
            )

            if not out.isOpened():
                raise RuntimeError("无法创建视频文件")

            start_frame = int(self.video_processor.start_time * self.video_processor.fps)
            end_frame = int(self.video_processor.end_time * self.video_processor.fps)

            for frame_num in range(start_frame, end_frame):
                self.video_processor.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = self.video_processor.cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    cropped = self.video_processor.get_cropped_frame(frame)
                    out.write(cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR))

            out.release()
            messagebox.showinfo("导出完成", f"视频已导出到 {output_path}")
        except Exception as e:
            messagebox.showerror("导出错误", str(e))

    def export_frames(self):
        if not self.video_processor:
            return

        output_dir = "output_frames"
        try:
            os.makedirs(output_dir, exist_ok=True)
            start_frame = int(self.video_processor.start_time * self.video_processor.fps)
            end_frame = int(self.video_processor.end_time * self.video_processor.fps)

            for frame_num in range(start_frame, end_frame):
                self.video_processor.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = self.video_processor.cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    cropped = self.video_processor.get_cropped_frame(frame)
                    frame_path = os.path.join(output_dir, f"frame_{frame_num:05d}.png")
                    cv2.imwrite(frame_path, cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR))

            messagebox.showinfo("导出完成", f"已导出 {end_frame - start_frame} 帧到 {output_dir} 目录")
        except Exception as e:
            messagebox.showerror("导出错误", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    try:
        app = VideoEditorGUI(root)
        app.load_video(r"C:\Users\74198\Desktop\2025.4.26.1m.1.0.jpeg_C001H001S0001.avi")  # 修改为实际路径
        root.mainloop()
    except Exception as e:
        messagebox.showerror("致命错误", str(e))

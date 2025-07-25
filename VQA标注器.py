import os
import json
from enum import Enum
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from PIL import Image, ImageTk
from dataclasses import dataclass, field

class DrawMode(Enum):
    NONE = "none"
    RECT = "rect"
    POLY = "poly"
    POINT = "point"

    def __repr__(self):
        return self.value

class Color(Enum):
    RED = 'red'
    BLUE = 'blue'
    GREEN = 'green'

"""实现在画布上绘制矩形、多边形、点"""
class DrawingCanvas(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.image_item = None
        self.current_mode = DrawMode.NONE
        self.current_points = []
        self.current_item = None
        self.items = []

    def set_mode(self, mode):
        """设置绘图模式: 矩形、多边形、点"""
        self.current_mode = mode
        self.current_points.clear()
        self.clear_item()

    def on_left_click(self, event):
        """
        处理鼠标左键点击：对于绘制矩形，开始绘图第一个点；对于绘制多边形，继续绘制新的边；对于绘制点，覆盖前面的点
        """
        if self.current_mode is DrawMode.NONE:
            return 
        self.clear_item()
        x, y = event.x, event.y
        if self.current_mode == DrawMode.RECT:
            self.current_points = [x, y, x, y]
            self.current_item = self.create_rectangle(*self.current_points, outline=Color.RED.value)
        elif self.current_mode == DrawMode.POLY:
            self.current_points.extend([x, y])
            self.current_item = self.create_polygon(self.current_points, outline=Color.BLUE.value, fill="")
        elif self.current_mode == DrawMode.POINT:
            self.current_points = [x, y]
            self.current_item = self.create_oval(x-2, y-2, x+2, y+2, fill=Color.GREEN.value)

    def on_drag(self, event):
        """处理鼠标左键拖动：对于绘制矩形，矩形框大小跟随鼠标变化，松开鼠标时，结束绘制；其它模式无影响"""
        if self.current_mode == DrawMode.RECT and self.current_item:
            self.current_points[2:] = [event.x, event.y]
            self.coords(self.current_item, *self.current_points)

    def on_right_click(self, event):
        """处理鼠标右键点击：结束绘制，并返回标注类型和坐标。对于绘制多边形，会自动闭合多边形；"""
        if self.current_item is None or self.current_mode == DrawMode.NONE:
            return None
        if self.current_mode == DrawMode.POLY:
            self.delete(self.current_item)
            self.current_item = self.create_polygon(self.current_points, outline="blue", fill="")
        self.items.append(self.current_item)
        ret = {
            "mode": self.current_mode,
            "points": self.current_points.copy(),
            "draw_id": self.current_item 
        }
        self.current_item = None
        self.current_mode= None
        self.current_points.clear()
        return ret

    def load_image(self, img, offsets=None):
        if offsets is None:
            offsets = (0, 0)
        self.image_item = self.create_image(*offsets, anchor=tk.NW, image=img)
        self.tag_lower(self.image_item)  # 将图像置于底层

    def load_draw(self, mode, pts):
        if mode == DrawMode.RECT and len(pts) == 4:
            self.current_item = self.create_rectangle(*pts, outline=Color.RED.value)
        elif mode == DrawMode.POLY and len(pts) >= 6:
            self.current_item = self.create_polygon(pts, outline=Color.BLUE.value, fill="")
        elif mode == DrawMode.POINT:
            x, y = pts[:2]
            self.current_item = self.create_oval(x-8, y-8, x+8, y+8, fill=Color.GREEN.value)
        else:
            return None
        self.items.append(self.current_item)
        self.current_item = None
        return self.items[-1]

    def clear_item(self):
        """清除当前未完成的绘图"""
        if self.current_item:
            self.delete(self.current_item)
            self.current_points.clear()
            self.current_item = None

    def clear_all(self):
        """清除所有绘图元素"""
        self.clear_item()
        for item_id in self.items:
            self.delete(item_id)
        self.items.clear()

    def delete_item(self, item_id):
        """根据ID删除特定的绘图元素"""
        try:
            self.items.remove(item_id)
        except ValueError:
            return False
        self.delete(item_id)
        return True

    def reset(self):
        self.delete("all")
        self.image_item = None
        self.current_mode = DrawMode.NONE
        self.current_points.clear()
        self.current_item = None
        self.items.clear()

@dataclass
class VisualAnnotation:
    """视觉标注基类"""
    coords: list[float] 
    mode: DrawMode = DrawMode.NONE

    def __repr__(self):
        return f"{self.mode.value}, {self.coords}"

@dataclass
class QAAnnotation:
    """问答标注项"""
    role: str  # "human" or "gpt"
    text: str
    visual_refs: list[VisualAnnotation] | None

@dataclass
class ImageAnnotation:
    """单张图像的完整标注"""
    image: str = ""
    conversations: list[QAAnnotation] = field(default_factory=list)

class ImageQAAnnotator:
    def __init__(self, root):
        self.root = root
        self.root.title("多轮问答标注工具")
        self.root.geometry("1200x800")

        # 初始化状态
        self.image_files: list[str] = []
        self.all_annotations: dict[str, list[QAAnnotation]] = {} # filename : ImageAnnotation
        # 当前图像
        self.current_image_index = 0
        self.current_original_image = None
        self.current_draw_info: list = []
        self.current_annotation: list[QAAnnotation] = []
        self.is_query_input = False
        # 缩放设置
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.fit_to_window = True
        # 创建界面
        self.setup_ui()

    def setup_ui(self):
        """设置用户界面"""
        # 主布局
        self.main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # 左侧主工作区
        self.left_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.left_frame, weight=4)

        # 右侧侧边栏
        self.right_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.right_frame, weight=1)

        # 顶部工具栏
        self.setup_toolbar()

        # 图像显示区
        self.setup_image_display()

        # 问答标注区
        self.setup_qa_annotation()

        # 右侧面板
        self.setup_right_panel()

        # 状态栏
        self.setup_status_bar()

    def setup_toolbar(self):
        """设置顶部工具栏"""
        toolbar = ttk.Frame(self.left_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        # 文件操作按钮
        ttk.Button(toolbar, text="打开文件夹", command=self.open_images_folder).pack(side=tk.LEFT, padx=2)
        # ttk.Button(toolbar, text="新建标注", command=self.save_annotations).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="保存标注", command=self.save_annotations).pack(side=tk.LEFT, padx=2)

        # 导航按钮
        ttk.Button(toolbar, text="上一张", command= lambda : self.jump2image((self.current_image_index - 1))).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="下一张", command= lambda : self.jump2image((self.current_image_index + 1))).pack(side=tk.LEFT, padx=2)

        # 缩放控制
        zoom_frame = ttk.Frame(toolbar)
        zoom_frame.pack(side=tk.RIGHT, padx=5)

        ttk.Button(zoom_frame, text="适应窗口", command=self.fit_window).pack(side=tk.LEFT, padx=2)
        ttk.Button(zoom_frame, text="实际大小", command=self.reset_zoom).pack(side=tk.LEFT, padx=2)
        # ttk.Button(zoom_frame, text="放大", command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        # ttk.Button(zoom_frame, text="缩小", command=self.zoom_out).pack(side=tk.LEFT, padx=2)

        self.zoom_label = ttk.Label(zoom_frame, text="缩放: 适应窗口")
        self.zoom_label.pack(side=tk.LEFT, padx=5)

    def setup_image_display(self):
        """设置图像显示区"""
        frame = ttk.LabelFrame(self.left_frame, text="图像显示")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 初始化绘图管理器
        self.drawing_canvas = DrawingCanvas(frame, bg="white", cursor="cross")
        self.drawing_canvas.pack(fill=tk.BOTH, expand=True)

        # 绑定事件
        self.drawing_canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.drawing_canvas.bind("<Button-1>", self.drawing_canvas.on_left_click)
        self.drawing_canvas.bind("<B1-Motion>", self.drawing_canvas.on_drag)
        self.drawing_canvas.bind("<Button-3>", self.on_draw_finished)
        # self.drawing_canvas.bind("<Configure>", self.resize_draw_canvas)

    def setup_qa_annotation(self):
        """设置问答标注区"""
        frame = ttk.LabelFrame(self.left_frame, text="问答标注")
        frame.pack(fill=tk.X, padx=5, pady=5)

        # 创建一个水平分割的框架，用于将绘图工具栏和问答输入并列
        split_frame = ttk.Frame(frame)
        split_frame.pack(fill=tk.X, pady=5)

        # 绘图工具栏框架
        drawing_toolbar_frame = ttk.Frame(split_frame)
        drawing_toolbar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # 绘图工具栏按钮
        toolbar_buttons_frame = ttk.Frame(drawing_toolbar_frame)
        toolbar_buttons_frame.pack(fill=tk.X, pady=5)

        ttk.Button(toolbar_buttons_frame, text="矩形", 
            command=lambda : (self.drawing_canvas.set_mode(DrawMode.RECT), self.status_var.set(f"绘图模式: {DrawMode.RECT.name}"))
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_buttons_frame, text="多边形", 
            command=lambda : (self.drawing_canvas.set_mode(DrawMode.POLY), self.status_var.set(f"绘图模式: {DrawMode.POLY.name}"))
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_buttons_frame, text="点", 
            command=lambda : (self.drawing_canvas.set_mode(DrawMode.POINT), self.status_var.set(f"绘图模式: {DrawMode.POINT.name}"))
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_buttons_frame, text="清除当前", 
            command=lambda: (self.drawing_canvas.clear_item(), self.status_var.set(f"清除当前绘图"))
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_buttons_frame, text="清除所有", 
            command=lambda: (self.drawing_canvas.clear_all(), self.current_draw_info.clear(), self.status_var.set(f"清除所有绘图"))
        ).pack(side=tk.LEFT, padx=2)

        # 绘图结果展示框架
        drawing_result_frame = ttk.Frame(drawing_toolbar_frame)
        drawing_result_frame.pack(fill=tk.X, pady=5)

        # 问答输入框架
        qa_frame = ttk.Frame(split_frame)
        qa_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Label(qa_frame, text="问题:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.question_entry = ttk.Entry(qa_frame, width=75)
        self.question_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.question_entry.bind("<Button-1>", self.on_click_query_entry)

        ttk.Label(qa_frame, text="回答:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.answer_entry = ttk.Entry(qa_frame, width=75)
        self.answer_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.answer_entry.bind("<Button-1>", self.on_click_anwser_entry)

        self.add_qa_button = ttk.Button(qa_frame, text="添加问答对", command=self.add_qa_pair)
        self.add_qa_button.grid(row=0, column=2, rowspan=2, padx=5)

    def setup_right_panel(self):
        """设置右侧面板"""
        # 图像列表
        img_list_frame = ttk.LabelFrame(self.right_frame, text="图像列表")
        img_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.image_tree = ttk.Treeview(img_list_frame, columns=("status", "name"), show="headings")
        self.image_tree.heading("status", text="状态")
        self.image_tree.heading("name", text="图像名称")
        self.image_tree.column("status", width=20, anchor=tk.CENTER)
        self.image_tree.column("name", width=180, anchor=tk.W)

        scrollbar = ttk.Scrollbar(img_list_frame, orient=tk.VERTICAL, command=self.image_tree.yview)
        self.image_tree.configure(yscrollcommand=scrollbar.set)

        self.image_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.image_tree.bind("<<TreeviewSelect>>", self.on_image_selected)

        # 问答对列表
        qa_list_frame = ttk.LabelFrame(self.right_frame, text="已标注问答对")
        qa_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.qa_listbox = tk.Listbox(qa_list_frame)
        scrollbar = ttk.Scrollbar(qa_list_frame, orient=tk.VERTICAL, command=self.qa_listbox.yview)
        self.qa_listbox.configure(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(qa_list_frame)
        button_frame.pack(fill=tk.X, pady=5)

        ttk.Button(button_frame, text="编辑", command=self.edit_qa_pair).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="删除", command=self.delete_qa_pair).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="清空", command=self.clear_qa_pairs).pack(side=tk.LEFT, padx=2)

        self.qa_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_status_bar(self):
        """设置状态栏"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=5, pady=2)
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)

        # self.progress_var = tk.DoubleVar()
        # ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100).pack(side=tk.RIGHT, fill=tk.X, expand=True)

    def open_images_folder(self):
        """打开图像文件夹"""
        folder = filedialog.askdirectory(title="选择图像文件夹")
        if not folder:
            return

        self.images_folder = folder
        self.ann_save_folder = os.path.join(folder, "outputs")
        os.makedirs(self.ann_save_folder, exist_ok=True)
        self.image_files = [
            f for f in os.listdir(folder)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))
        ]

        if not self.image_files:
            messagebox.showwarning("警告", "没有找到图像文件")
            return

        self.status_var.set(f"加载文件夹: {self.images_folder}")

        # 加载已有标注
        self.load_existing_annotations()
        # 更新图像列表
        self.update_image_list()

        # 加载第一张图像
        if self.image_files:
            self.current_image_index = 0
            self.load_current_image()
    
    def load_current_image(self):
        """加载当前图像"""
        if not self.image_files or self.current_image_index >= len(self.image_files):
            return

        file_name = self.image_files[self.current_image_index]
        current_image_path = os.path.join(self.images_folder, file_name)
        try:
            # 加载图像
            self.current_original_image = Image.open(current_image_path)
            # 当前标注
            self.current_annotation = self.all_annotations.get(file_name, []).copy()
            # 显示图像
            self.fit_window()
            # 更新问答对列表
            self.update_qa_list()
            # 更新状态
            self.update_image_list()
            self.status_var.set(f"已加载: {file_name}")
        except Exception as e:
            messagebox.showerror("错误", f"加载图像失败: {str(e)}")

    def resize_draw_canvas(self, event):
        canvas_width = event.width
        canvas_height = event.height
        print("canvas_width: ", canvas_width, canvas_height)
        if self.current_original_image:
            img_width, img_height = self.current_original_image.size
            width_ratio = canvas_width / img_width
            height_ratio = canvas_height / img_height
            self.zoom_factor = min(width_ratio, height_ratio)
            if self.zoom_factor < self.min_zoom:
                self.zoom_factor = self.min_zoom
            
    def display_image(self):
        """显示当前图像"""
        # 缩放图像
        scaled_image = self.current_original_image.resize((self.current_img_width, self.current_img_height), Image.LANCZOS)
        self.current_image = ImageTk.PhotoImage(scaled_image)
        # 显示图像
        self.drawing_canvas.reset()
        self.drawing_canvas.load_image(self.current_image, (self.x_offset, self.y_offset))
        self.drawing_canvas.config(scrollregion=self.drawing_canvas.bbox("all"))

    def on_draw_finished(self, event):
        ref = self.drawing_canvas.on_right_click(event)
        if ref:
            # 转换成像素坐标
            ref['points'] = [(x-self.x_offset)/self.zoom_factor if i%2==0 else (x-self.y_offset)/self.zoom_factor for i, x in enumerate(ref['points']) ]
            ref["is_Q"] = self.is_query_input
            self.current_draw_info.append(ref)
            self.status_var.set(f"完成绘制：{self.current_draw_info[-1]}")

    def on_click_query_entry(self, event):
        self.is_query_input = True
    
    def on_click_anwser_entry(self, event):
        self.is_query_input = False
        
    def add_qa_pair(self):
        """添加问答对"""
        question = self.question_entry.get().strip()
        answer = self.answer_entry.get().strip()

        if not question or not answer:
            messagebox.showwarning("警告", "问题和回答不能为空")
            return

        # 创建问答对
        visual_refs_query = []
        visual_refs_anwser = []
        # 只在有新的绘制操作时才使用视觉标注
        if self.current_draw_info:
            for draw_item in self.current_draw_info:
                ref = VisualAnnotation(mode=draw_item["mode"], coords=draw_item["points"])
                if draw_item["is_Q"]:
                    visual_refs_query.append(ref)
                else:
                    visual_refs_anwser.append(ref)
            self.current_draw_info = []
        question_ann = QAAnnotation(role="human", text=question, visual_refs=visual_refs_query or None)
        answer_ann = QAAnnotation(role="gpt", text=answer, visual_refs=visual_refs_anwser or None)

        # 添加到当前标注
        self.current_annotation.extend([question_ann, answer_ann])

        # 更新UI
        self.update_qa_list()
        # 添加问答对后重置绘制标志
        self.drawing_canvas.clear_all()
        self.question_entry.delete(0, tk.END)
        self.answer_entry.delete(0, tk.END)

    def delete_qa_pair(self, index=None):
        """删除选中的问答对"""
        if index is None:
            selected = self.qa_listbox.curselection()
            if not selected:
                return
            index = selected[0] // 3  # 每两个列表项对应一个问答对
        del self.current_annotation[index*2:index*2+2]
        self.qa_listbox.delete(index*3,index*3+2)

    def clear_qa_pairs(self):
        """清空当前图像的所有问答对"""
        if messagebox.askyesno("确认", "确定要清空当前图像的所有标注吗？"):
            self.current_annotation.clear()
            self.qa_listbox.delete(0, self.qa_listbox.size()-1)

    def edit_qa_pair(self):
        """编辑选中的问答对"""
        selected = self.qa_listbox.curselection()
        # print("qs sz: ", self.qa_listbox.size(), selected, len(self.current_annotation))
        if not selected:
            return
        index = selected[0] // 3   # 每两个列表项对应一个问答对
        # 在输入框中显示当前内容
        self.question_entry.delete(0, tk.END)
        self.question_entry.insert(0, self.current_annotation[index*2].text)

        self.answer_entry.delete(0, tk.END)
        self.answer_entry.insert(0, self.current_annotation[index*2+1].text)

        self.show_qa_pair(index*2)
        self.delete_qa_pair(index)

    def update_qa_list(self):
        """更新问答对列表"""
        self.qa_listbox.delete(0, tk.END)
        count = 0
        for conv in self.current_annotation:
            text = "A"
            if conv.role in ["human", "user"]:
                text = "Q"
                count += 1
            text += f"{count}: {conv.text}"
            if conv.visual_refs:
                for ref in conv.visual_refs:
                    text += f"<region>{ref.mode.name}:{ref.coords}"
                text += "<region>"
            self.qa_listbox.insert(tk.END, text)
            if text[0] == "A":
                self.qa_listbox.insert(tk.END, '-'*50)

    def show_qa_pair(self, index):
        # 加载已有标注
        if index <0 or index >= len(self.current_annotation):
            self.status_var.set(f"标注{index}超出")
            return
        self.drawing_canvas.clear_all()
        ann = self.current_annotation[index // 2 * 2]
        if ann.visual_refs:
            for ref in ann.visual_refs:
                canvas_coords = [(x*self.zoom_factor+self.x_offset) if i%2==0 else (x*self.zoom_factor+self.y_offset) for i, x in enumerate(ref.coords) ]
                self.current_draw_info.append(
                    {
                        "mode": ref.mode,
                        "points": canvas_coords,
                        "draw_id": self.drawing_canvas.load_draw(ref.mode, canvas_coords)
                    }
                )

    def update_image_list(self):
        """更新图像列表"""
        self.image_tree.delete(*self.image_tree.get_children())
        for filename in self.image_files:
            status = "✓" if self.all_annotations.get(filename) else ""
            tags = ("annotated",) if status else ()
            self.image_tree.insert("", tk.END, values=(status, filename), tags=tags)

        # 选中当前图像
        self.image_tree.tag_configure("annotated", background="#e6ffe6")
        if self.image_files and 0 <= self.current_image_index < len(self.image_files):
            items = self.image_tree.get_children()
            if items:
                self.image_tree.selection_set(items[self.current_image_index])
                self.image_tree.see(items[self.current_image_index])

    def on_image_selected(self, event):
        """图像列表选择事件"""
        selected = self.image_tree.selection()
        if not selected:
            return

        index = self.image_tree.index(selected[0])
        if index != self.current_image_index:
            self.jump2image(index)

    def jump2image(self, index):
        if index >= len(self.image_files) or index < 0:
            self.status_var.set(f"{index}超出")
            return

        self.current_image_index = index
        self.load_current_image()

    def save_annotations(self):
        """保存标注数据"""
        if not hasattr(self, "images_folder") or not self.images_folder:
            messagebox.showwarning("警告", "请先打开图像文件夹")
            return
        file_name = self.image_files[self.current_image_index]
        if len(self.current_annotation) == 0:
            if file_name in self.all_annotations:
                del self.all_annotations[file_name]
            return
        # 更新当前标注
        self.all_annotations[file_name] = self.current_annotation
        # 保存到文件
        save_path = os.path.join(self.images_folder, "annotations.json")

        try:
            # 转换为可序列化的字典
            annotations_data = []
            for image_id, conversations in self.all_annotations.items():
                new_conversations = []
                for qa in conversations:
                    qa_dict = {
                        "from": qa.role,
                        "value": qa.text
                    }
                    if qa.visual_refs:
                        qa_dict["visual_refs"] = [{
                            "mode": ref.mode.name,
                            "coords": [int(round(x)) for x in ref.coords]
                        } for ref in qa.visual_refs]
                    new_conversations.append(qa_dict)
                annotations_data.append({
                    "image": image_id,
                    "conversations": new_conversations
                })

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(annotations_data, f, ensure_ascii=False, indent=2)

            self.root.after(0, lambda: self.status_var.set("标注已保存：" + save_path))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"保存失败: {str(e)}"))


    def load_existing_annotations(self):
        """加载已有的标注数据"""
        if not hasattr(self, "images_folder") or not self.images_folder:
            return

        annotations_file = os.path.join(self.images_folder, "annotations.json")
        if not os.path.exists(annotations_file):
            return

        try:
            with open(annotations_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data:
                conversations = []
                for conv in item["conversations"]:
                    visual_refs = None
                    if "visual_refs" in conv:
                        visual_refs = [
                            VisualAnnotation(mode=DrawMode[ref["mode"]], coords=ref["coords"]) 
                            for ref in conv["visual_refs"]
                        ]
                    qa = QAAnnotation(role=conv["from"], text=conv["value"], visual_refs=visual_refs)
                    conversations.append(qa)
                self.all_annotations[item["image"]] = conversations
            self.status_var.set(f"已加载 {len(self.all_annotations)} 条标注")
        except Exception as e:
            messagebox.showerror("错误", f"加载标注失败: {str(e)}")

    # def update_progress(self):
    #     """更新进度条"""
    #     if not self.image_files:
    #         return
    #     annotated = len(self.all_annotations)
    #     total = len(self.image_files)
    #     self.progress_var.set((annotated / total) * 100 if total > 0 else 0)

    def check_current_image(self):
        return self.current_original_image is not None
    # 缩放功能
    def zoom(self, x=None, y=None, scale_up=0):
        if not self.check_current_image():
            return
        if x is None:
            x = self.drawing_canvas.winfo_width()//2
            y = self.drawing_canvas.winfo_height()//2
        if scale_up == 0:
            self.zoom_factor = 1.0
        elif scale_up > 0:
            self.zoom_factor = min(self.zoom_factor * 1.1, self.max_zoom)
        else:
            self.zoom_factor = max(self.zoom_factor / 1.1, self.min_zoom)

        pos_x = (x - self.x_offset)/self.current_img_width
        pos_y = (y - self.y_offset)/self.current_img_height

        img_width, img_height = self.current_original_image.size
        self.current_img_width = int(img_width * self.zoom_factor)
        self.current_img_height = int(img_height * self.zoom_factor)
        self.x_offset = (x - int(self.current_img_width*pos_x))
        self.y_offset = (y - int(self.current_img_height*pos_y))
        self.zoom_label.config(text=f"缩放: {int(self.zoom_factor * 100)}%")
        self.display_image()
    
    def reset_zoom(self):
        self.zoom(scale_up=0)

    def fit_window(self):
        """适应窗口"""
        if self.current_original_image is None:
            return 
        self.fit_to_window = True
        canvas_width = self.drawing_canvas.winfo_width()
        canvas_height = self.drawing_canvas.winfo_height()
        img_width, img_height = self.current_original_image.size
        width_ratio = canvas_width / img_width
        height_ratio = canvas_height / img_height
        self.zoom_factor = min(width_ratio, height_ratio)
        if self.zoom_factor < self.min_zoom:
            self.zoom_factor = self.min_zoom
        self.current_img_width = int(self.current_original_image.width * self.zoom_factor)
        self.current_img_height = int(self.current_original_image.height * self.zoom_factor)
        self.x_offset = (canvas_width -  self.current_img_width) // 2
        self.y_offset = (canvas_height - self.current_img_height) // 2
        self.zoom_label.config(text="缩放: 适应窗口")
        self.display_image()
        self.fit_to_window = False

    def on_mousewheel(self, event):
        """鼠标滚轮缩放"""
        # x, y = event.x, event.y
        x, y = self.drawing_canvas.canvasx(event.x), self.drawing_canvas.canvasy(event.y)
        if event.delta > 0 or event.num == 4:  # 向上滚动
            self.zoom(x, y, 1)
        else:  # 向下滚动
            self.zoom(x, y, -1)

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageQAAnnotator(root)
    root.mainloop()
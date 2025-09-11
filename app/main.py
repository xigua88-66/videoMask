import sys
import os
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QWidget, 
                             QVBoxLayout, QHBoxLayout, QListWidget, QFileDialog, QDialog, 
                             QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox, 
                             QLabel, QStackedWidget, QColorDialog, QToolBar, QSlider, QSizePolicy,
                             QInputDialog, QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QPixmap, QPainter, QPen, QAction, QColor, QPaintEvent, QFont, QFontMetrics

from core.video_processor import extract_frames, create_video

# 配置日志输出到文件
# 创建日志目录
log_dir = Path.home() / "videoMask_logs"
log_dir.mkdir(exist_ok=True)

# 配置日志格式
log_format = '%(asctime)s - %(levelname)s - %(message)s'
log_file = log_dir / f"videoMask_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format=log_format,
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"🚀 视频标注工具启动 - 日志文件: {log_file}")

class NewTaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建新任务")

        self.layout = QFormLayout(self)

        self.task_name = QLineEdit(self)
        self.video_path = QLineEdit(self)
        self.video_path_button = QPushButton("选择视频", self)
        self.video_path_button.clicked.connect(self.select_video_file)
        self.frame_interval = QSpinBox(self)
        self.frame_interval.setRange(1, 1000)
        self.frame_interval.setValue(30) # 默认每30帧抽一帧

        self.layout.addRow("任务名称:", self.task_name)
        self.layout.addRow("视频路径:", self.video_path)
        self.layout.addRow("", self.video_path_button)
        self.layout.addRow("抽帧间隔:", self.frame_interval)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        self.layout.addWidget(self.buttons)

    def select_video_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov)")
        if file_name:
            self.video_path.setText(file_name)

    def get_task_info(self):
        return {
            "task_name": self.task_name.text(),
            "video_path": self.video_path.text(),
            "frame_interval": self.frame_interval.value()
        }


class AnnotationLabel(QLabel):
    """自定义QLabel，用于处理鼠标事件以进行标注。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # 修复显示问题：使用更合理的尺寸策略
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(100, 100)  # 设置最小尺寸
        self.setScaledContents(False)  # 禁用自动缩放，我们手动控制
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 确保可以接收键盘事件

        self._pixmap = QPixmap() # 存储原始、未缩放的图像
        
        # 坐标转换参数
        self.scale_factor = 1.0
        self.pixmap_offset = QPointF(0, 0)
        
        self.start_point = QPointF()
        self.end_point = QPointF()
        self.drawing = False
        self.shapes = [] # 存储所有已绘制的图形信息
        self.current_shape_type = 'rectangle' # 'rectangle' or 'polygon'
        # 统一颜色类型为 QColor，从源头解决序列化问题
        self.current_color = QColor(Qt.GlobalColor.red)
        self.current_thickness = 2
        self.current_font_size = 16
        self.current_bold_state = False
        
        # 用于移动和编辑
        self.selected_shape = None
        self.dragging = False
        self.drag_offset = QPointF()
        self.editing_mode = False  # 是否处于编辑模式
        self.last_click_time = 0   # 用于双击检测
        self.is_displaying_saved_annotations = False  # 是否显示已保存的标注图片
        
        # 针对多边形
        self.current_polygon_points = []

    def set_new_pixmap(self, pixmap):
        """设置新的原始图像并更新显示。"""
        print(f"🔧 [DEBUG] set_new_pixmap called - pixmap null: {pixmap.isNull()}, size: {pixmap.width()}x{pixmap.height()}")
        self._pixmap = pixmap
        # 立即尝试显示，如果控件尺寸无效，就显示原始图片让Qt处理
        self._update_scaled_pixmap_and_transform()

    def _update_scaled_pixmap_and_transform(self):
        """
        核心函数：根据控件当前大小缩放并显示图像，并计算坐标转换参数。
        """
        print(f"📐 [DEBUG] _update_scaled_pixmap_and_transform called")
        print(f"📐 [DEBUG] Widget size: {self.width()}x{self.height()}")
        print(f"📐 [DEBUG] Original pixmap null: {self._pixmap.isNull()}")
        
        if not self._pixmap.isNull():
            print(f"📐 [DEBUG] Original pixmap size: {self._pixmap.width()}x{self._pixmap.height()}")
        
        if self._pixmap.isNull():
            print("❌ [DEBUG] No pixmap, setting empty")
            # 如果没有图片，设置空图片
            self._set_pixmap_directly(QPixmap())
            return

        if self.width() <= 1 or self.height() <= 1:
            print("⚠️ [DEBUG] Widget size invalid, showing original pixmap")
            # 如果控件尺寸无效，直接显示原始图片，让Qt自动处理
            self._set_pixmap_directly(self._pixmap)
            # 设置默认值，避免后续计算出错
            self.scale_factor = 1.0
            self.pixmap_offset = QPointF(0, 0)
            return

        print("✅ [DEBUG] Widget size valid, calculating scaled pixmap")
        # 1. 计算缩放后的 pixmap 和它的尺寸 (保持宽高比)
        scaled_pixmap = self._pixmap.scaled(self.size(), 
                                             Qt.AspectRatioMode.KeepAspectRatio, 
                                             Qt.TransformationMode.SmoothTransformation)
        
        print(f"📏 [DEBUG] Scaled pixmap size: {scaled_pixmap.width()}x{scaled_pixmap.height()}")
        
        # 2. 计算偏移量 (用于在窗口中居中显示)，并修复 DeprecationWarning
        self.pixmap_offset.setX((self.width() - scaled_pixmap.width()) / 2)
        self.pixmap_offset.setY((self.height() - scaled_pixmap.height()) / 2)
        print(f"📍 [DEBUG] Offset: ({self.pixmap_offset.x()}, {self.pixmap_offset.y()})")

        # 3. 计算缩放因子
        if scaled_pixmap.width() > 0:
            self.scale_factor = self._pixmap.width() / scaled_pixmap.width()
        else:
            self.scale_factor = 1.0
        
        print(f"🔢 [DEBUG] Scale factor: {self.scale_factor}")
        
        # 4. 显示缩放后的图片
        print("🖼️ [DEBUG] Calling _set_pixmap_directly with scaled pixmap")
        self._set_pixmap_directly(scaled_pixmap)

    def _set_pixmap_directly(self, pixmap):
        """直接设置pixmap，绕过我们自己的setPixmap重写"""
        print(f"🎯 [DEBUG] _set_pixmap_directly called - pixmap null: {pixmap.isNull()}")
        if not pixmap.isNull():
            print(f"🎯 [DEBUG] Setting pixmap size: {pixmap.width()}x{pixmap.height()}")
        
        # 调用父类的setPixmap
        QLabel.setPixmap(self, pixmap)
        
        # 验证设置是否成功
        current_pixmap = self.pixmap()
        if current_pixmap:
            print(f"✅ [DEBUG] Verification: current pixmap size: {current_pixmap.width()}x{current_pixmap.height()}")
        else:
            print(f"❌ [DEBUG] Verification FAILED: no current pixmap!")
        
        print(f"🎯 [DEBUG] setPixmap completed - Label visible: {self.isVisible()}")

    def screen_to_pixmap_pos(self, screen_pos):
        """屏幕坐标 -> 图片真实坐标"""
        # 确保输入是 QPointF 类型
        screen_pos_f = QPointF(screen_pos)
        # 减去偏移量，回到缩放后图片的左上角(0,0)
        adjusted_pos = screen_pos_f - self.pixmap_offset
        # 乘以缩放比例，得到真实坐标
        return adjusted_pos * self.scale_factor

    def pixmap_to_screen_pos(self, pixmap_pos):
        """图片真实坐标 -> 屏幕坐标"""
        # 除以缩放比例
        scaled_pos = pixmap_pos / self.scale_factor
        # 加上偏移量
        return scaled_pos + self.pixmap_offset

    def resizeEvent(self, event):
        """当控件大小改变时，自动重新缩放图像并更新转换参数。"""
        print(f"🔄 [DEBUG] resizeEvent called - new size: {self.width()}x{self.height()}")
        super().resizeEvent(event)
        self._update_scaled_pixmap_and_transform()

    def setPixmap(self, pixmap):
        # 重写 setPixmap 为空方法，防止外部意外调用导致循环
        # 我们只使用 set_new_pixmap 来设置图片
        pass

    def set_bold(self, bold):
        if self.selected_shape and self.editing_mode:
            # 只有在编辑模式下才修改选中对象的粗体状态（仅适用于文本）
            if self.selected_shape['type'] == 'text':
                self.selected_shape['bold'] = bold
                print(f"📝 [DEBUG] Changed selected text bold to {bold} in edit mode")
                self.update()
        else:
            # 否则设置当前工具的粗体状态
            self.current_bold_state = bold

    def set_shape_type(self, shape_type):
        self.current_shape_type = shape_type
        self.current_polygon_points = [] # 切换工具时重置当前多边形
        self.update()

    def set_color(self, color):
        if self.selected_shape and self.editing_mode:
            # 只有在编辑模式下才修改选中对象的颜色
            self.selected_shape['color'] = color
            print(f"🎨 [DEBUG] Changed selected {self.selected_shape['type']} color in edit mode")
            self.update()
        else:
            # 否则设置当前工具的颜色
            self.current_color = color

    def set_thickness(self, thickness):
        if self.selected_shape and self.editing_mode:
            # 只有在编辑模式下才修改选中对象的粗细（仅适用于矩形和多边形）
            if self.selected_shape['type'] in ['rectangle', 'polygon']:
                self.selected_shape['thickness'] = thickness
                print(f"✏️ [DEBUG] Changed selected {self.selected_shape['type']} thickness to {thickness} in edit mode")
                self.update()
        else:
            # 否则设置当前工具的粗细
            self.current_thickness = thickness

    def set_font_size(self, size):
        if self.selected_shape and self.editing_mode:
            # 只有在编辑模式下才修改选中对象的字号（仅适用于文本）
            if self.selected_shape['type'] == 'text':
                self.selected_shape['font_size'] = size
                print(f"🔤 [DEBUG] Changed selected text font size to {size} in edit mode")
                self.update()
        else:
            # 否则设置当前工具的字号
            self.current_font_size = size

    def undo(self):
        if self.shapes:
            # 撤销最后（最新）添加的标注
            self.shapes.pop(-1)  # pop() 默认就是 -1，但明确写出来更清楚
            self.update()
            print(f"🔙 [DEBUG] Undo completed, remaining shapes: {len(self.shapes)}")

    def is_point_in_rect(self, point, rect_points):
        """检查点是否在矩形内"""
        if len(rect_points) != 2:
            return False
        p1, p2 = rect_points
        min_x, max_x = min(p1.x(), p2.x()), max(p1.x(), p2.x())
        min_y, max_y = min(p1.y(), p2.y()), max(p1.y(), p2.y())
        return min_x <= point.x() <= max_x and min_y <= point.y() <= max_y
    
    def is_point_in_polygon(self, point, polygon_points):
        """使用射线法检查点是否在多边形内"""
        x, y = point.x(), point.y()
        n = len(polygon_points)
        if n < 3:
            return False
        
        inside = False
        p1x, p1y = polygon_points[0].x(), polygon_points[0].y()
        
        for i in range(1, n + 1):
            p2x, p2y = polygon_points[i % n].x(), polygon_points[i % n].y()
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            import time
            current_time = time.time()
            is_double_click = (current_time - self.last_click_time) < 0.3  # 300ms内算双击
            self.last_click_time = current_time
            
            # 所有新创建的点都需要从屏幕坐标转换到图片坐标
            pixmap_pos = self.screen_to_pixmap_pos(event.pos())

            # 首先检查是否点击了任何已有的标注对象（从最新的开始检查）
            shape_clicked = False
            for shape in reversed(self.shapes):
                clicked = False
                
                if shape['type'] == 'text':
                    font = QFont()
                    font.setPointSize(shape['font_size'])
                    font.setBold(shape.get('bold', False))
                    fm = QFontMetrics(font)
                    text_rect = fm.boundingRect(shape['text'])
                    text_rect.moveTo(shape['pos'].toPoint())
                    text_rect.adjust(-5, -5, 5, 5)
                    clicked = text_rect.contains(pixmap_pos.toPoint())
                    
                elif shape['type'] == 'rectangle':
                    clicked = self.is_point_in_rect(pixmap_pos, shape['points'])
                    
                elif shape['type'] == 'polygon':
                    clicked = self.is_point_in_polygon(pixmap_pos, shape['points'])
                
                if clicked:
                    self.selected_shape = shape
                    
                    if is_double_click:
                        # 双击进入编辑模式
                        self.editing_mode = True
                        self.dragging = False
                        print(f"✏️ [DEBUG] {shape['type']} double-clicked, entering edit mode")
                        print(f"💡 [TIP] 现在可以修改颜色、粗细、字号等属性，按回车键确认编辑")
                    else:
                        # 单击进入移动模式
                        self.editing_mode = False
                        self.dragging = True
                        if shape['type'] == 'text':
                            self.drag_offset = pixmap_pos - shape['pos']
                        elif shape['type'] == 'rectangle':
                            # 对于矩形，记录相对于第一个点的偏移
                            self.drag_offset = pixmap_pos - shape['points'][0]
                        elif shape['type'] == 'polygon':
                            # 对于多边形，记录相对于第一个点的偏移
                            self.drag_offset = pixmap_pos - shape['points'][0]
                        print(f"🎯 [DEBUG] {shape['type']} single-clicked, entering move mode")
                    
                    shape_clicked = True
                    self.update()
                    return # Stop after finding one

            # 如果没有点击已有对象，清除选择并继续正常的绘制逻辑
            if self.selected_shape:
                self.selected_shape = None
                self.editing_mode = False
                print("🚫 [DEBUG] Selection cleared")
                self.update()
            
            if self.current_shape_type == 'rectangle':
                self.start_point = pixmap_pos
                self.end_point = pixmap_pos
                self.drawing = True
            elif self.current_shape_type == 'polygon':
                self.current_polygon_points.append(pixmap_pos)
                self.update() # 更新显示，画出点和线段
            elif self.current_shape_type == 'text':
                text, ok = QInputDialog.getText(self, '输入文字', '请输入要标注的文字:')
                if ok and text:
                    shape_info = {
                        "type": "text",
                        "text": text,
                        "pos": pixmap_pos,
                        "color": self.current_color,
                        "font_size": self.current_font_size,
                        "bold": self.current_bold_state
                    }
                    self.shapes.append(shape_info)
                    self.update()

    def mouseMoveEvent(self, event):
        pixmap_pos = self.screen_to_pixmap_pos(event.pos())

        if self.dragging and self.selected_shape and not self.editing_mode:
            if self.selected_shape['type'] == 'text':
                self.selected_shape['pos'] = pixmap_pos - self.drag_offset
            elif self.selected_shape['type'] == 'rectangle':
                # 移动矩形：创建新的tuple而不是修改现有的
                new_first_point = pixmap_pos - self.drag_offset
                offset = new_first_point - self.selected_shape['points'][0]
                new_second_point = self.selected_shape['points'][1] + offset
                # 创建新的tuple
                self.selected_shape['points'] = (new_first_point, new_second_point)
            elif self.selected_shape['type'] == 'polygon':
                # 移动多边形：创建新的tuple
                new_first_point = pixmap_pos - self.drag_offset
                offset = new_first_point - self.selected_shape['points'][0]
                new_points = tuple(point + offset for point in self.selected_shape['points'])
                self.selected_shape['points'] = new_points
            self.update()
        elif self.drawing and self.current_shape_type == 'rectangle':
            self.end_point = pixmap_pos
            self.update() # 请求重绘

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pixmap_pos = self.screen_to_pixmap_pos(event.pos())
            
            if self.dragging:
                self.dragging = False
                self.selected_shape = None
                self.update()

            elif self.drawing and self.current_shape_type == 'rectangle':
                self.drawing = False
                shape_info = {
                    "type": "rectangle",
                    "points": (self.start_point, self.end_point),
                    "color": self.current_color,
                    "thickness": self.current_thickness
                }
                self.shapes.append(shape_info)
                self.update()

    def keyPressEvent(self, event):
        # 按下 Enter 键
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if self.editing_mode and self.selected_shape:
                # 确认编辑并退出编辑模式
                self.editing_mode = False
                print(f"✅ [DEBUG] Edit mode confirmed for {self.selected_shape['type']}")
                print(f"🚫 [DEBUG] Exiting edit mode, selection cleared")
                self.selected_shape = None
                self.update()
            elif self.current_shape_type == 'polygon' and len(self.current_polygon_points) > 2:
                # 完成多边形绘制
                shape_info = {
                    "type": "polygon",
                    "points": tuple(self.current_polygon_points), # 改为tuple保持一致性
                    "color": self.current_color,
                    "thickness": self.current_thickness
                }
                self.shapes.append(shape_info)
                print(f"🔺 [DEBUG] Polygon completed with {len(self.current_polygon_points)} points")
                self.current_polygon_points = []
                self.update()
        elif event.key() == Qt.Key.Key_Escape:
            # Esc键退出编辑模式或取消选择
            if self.editing_mode:
                self.editing_mode = False
                print(f"❌ [DEBUG] Edit mode cancelled")
            if self.selected_shape:
                self.selected_shape = None
                print(f"🚫 [DEBUG] Selection cleared")
            self.update()
        super().keyPressEvent(event)


    def paintEvent(self, event, painter_override=None):
        # paintEvent 总是处理屏幕坐标
        if painter_override:
            painter = painter_override
        else:
            # 这是在屏幕上绘制
            super().paintEvent(event)
            painter = QPainter(self)

        # 只有在非已保存标注状态下才绘制标注（避免重影）
        if not self.is_displaying_saved_annotations:
            # 绘制所有已保存的图形
            for shape in self.shapes:
                pen = QPen(shape["color"], shape["thickness"] if "thickness" in shape else 1, Qt.PenStyle.SolidLine)
                painter.setPen(pen)

                if shape["type"] == "rectangle":
                    p1_screen = self.pixmap_to_screen_pos(shape["points"][0])
                    p2_screen = self.pixmap_to_screen_pos(shape["points"][1])
                    rect = self.get_rect_from_points(p1_screen, p2_screen)
                    painter.drawRect(*rect)
                elif shape["type"] == "polygon":
                    screen_points = [self.pixmap_to_screen_pos(p) for p in shape["points"]]
                    painter.drawPolygon(screen_points)
                elif shape["type"] == "text":
                    font = QFont()
                    font.setPointSize(shape["font_size"])
                    font.setBold(shape.get("bold", False)) # Handle old annotations
                    painter.setFont(font)
                    screen_pos = self.pixmap_to_screen_pos(shape["pos"])
                    painter.drawText(screen_pos.toPoint(), shape["text"])

        # 绘制选择高亮 (屏幕坐标)
        if self.selected_shape:
            # 根据模式选择不同的颜色：编辑模式用绿色，移动模式用蓝色
            highlight_color = QColor("green") if self.editing_mode else QColor("blue")
            pen = QPen(highlight_color, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            
            if self.selected_shape['type'] == 'text':
                font = QFont()
                font.setPointSize(self.selected_shape['font_size'])
                font.setBold(self.selected_shape.get("bold", False))
                fm = QFontMetrics(font)
                text_rect = fm.boundingRect(self.selected_shape['text'])
                
                # 移动到屏幕上的位置
                screen_pos = self.pixmap_to_screen_pos(self.selected_shape['pos'])
                text_rect.moveTo(screen_pos.toPoint())
                
                text_rect.adjust(-2, -2, 2, 2)
                painter.drawRect(text_rect)
                
                # 在编辑模式下显示额外的提示
                if self.editing_mode:
                    painter.setPen(QPen(QColor("green"), 1))
                    painter.drawText(int(text_rect.x()), int(text_rect.y()) - 5, "✏️ 编辑模式 - 回车确认")
                
            elif self.selected_shape['type'] == 'rectangle':
                # 绘制选中矩形的高亮边框
                p1_screen = self.pixmap_to_screen_pos(self.selected_shape['points'][0])
                p2_screen = self.pixmap_to_screen_pos(self.selected_shape['points'][1])
                rect = self.get_rect_from_points(p1_screen, p2_screen)
                # 扩大高亮区域
                highlight_rect = (rect[0] - 2, rect[1] - 2, rect[2] + 4, rect[3] + 4)
                painter.drawRect(*highlight_rect)
                
                # 在编辑模式下显示额外的提示
                if self.editing_mode:
                    painter.setPen(QPen(QColor("green"), 1))
                    painter.drawText(rect[0], rect[1] - 5, "✏️ 编辑模式 - 回车确认")
                
            elif self.selected_shape['type'] == 'polygon':
                # 绘制选中多边形的高亮边框
                screen_points = [self.pixmap_to_screen_pos(p) for p in self.selected_shape['points']]
                painter.drawPolygon(screen_points)
                
                # 在编辑模式下显示额外的提示
                if self.editing_mode and screen_points:
                    painter.setPen(QPen(QColor("green"), 1))
                    first_point = screen_points[0]
                    painter.drawText(int(first_point.x()), int(first_point.y()) - 5, "✏️ 编辑模式 - 回车确认")

        # 绘制正在画的矩形 (屏幕坐标)
        if self.drawing and self.current_shape_type == 'rectangle':
            pen = QPen(self.current_color, self.current_thickness, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            p1_screen = self.pixmap_to_screen_pos(self.start_point)
            p2_screen = self.pixmap_to_screen_pos(self.end_point)
            rect = self.get_rect_from_points(p1_screen, p2_screen)
            painter.drawRect(*rect)
        
        # 绘制正在画的多边形 (屏幕坐标)
        if self.current_shape_type == 'polygon' and self.current_polygon_points:
            pen = QPen(self.current_color, self.current_thickness, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            screen_points = [self.pixmap_to_screen_pos(p) for p in self.current_polygon_points]
            painter.drawPoints(screen_points)
            if len(self.current_polygon_points) > 1:
                painter.drawPolyline(screen_points)
        
        if not painter_override:
            painter.end()

    def get_rect_from_points(self, p1, p2):
        x = int(min(p1.x(), p2.x()))
        y = int(min(p1.y(), p2.y()))
        width = int(abs(p1.x() - p2.x()))
        height = int(abs(p1.y() - p2.y()))
        return x, y, width, height
        
class AnnotationWidget(QWidget):
    """
    一个用于显示和标注单张图片的控件。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # 工具栏
        self.toolbar = QToolBar()
        self.layout.addWidget(self.toolbar)

        self.rect_action = QAction("矩形", self)
        self.rect_action.setCheckable(True)
        self.rect_action.setChecked(True)
        self.rect_action.triggered.connect(lambda: self.set_shape_type('rectangle'))
        self.toolbar.addAction(self.rect_action)

        self.poly_action = QAction("多边形", self)
        self.poly_action.setCheckable(True)
        self.poly_action.triggered.connect(lambda: self.set_shape_type('polygon'))
        self.toolbar.addAction(self.poly_action)

        self.text_action = QAction("文本", self)
        self.text_action.setCheckable(True)
        self.text_action.triggered.connect(lambda: self.set_shape_type('text'))
        self.toolbar.addAction(self.text_action)


        self.toolbar.addSeparator()

        self.undo_action = QAction("撤销", self)
        self.undo_action.triggered.connect(lambda: self.debug_action_click("undo", self.undo_last_annotation))
        self.toolbar.addAction(self.undo_action)
        
        self.reset_action = QAction("重置", self)
        self.reset_action.triggered.connect(self.reset_annotations)
        self.toolbar.addAction(self.reset_action)

        self.toolbar.addSeparator()

        self.color_action = QAction("颜色", self)
        self.color_action.triggered.connect(self.select_color)
        self.toolbar.addAction(self.color_action)

        self.toolbar.addSeparator()

        self.thickness_label = QLabel("粗细: 2")
        self.toolbar.addWidget(self.thickness_label)

        self.thickness_slider = QSlider(Qt.Orientation.Horizontal)
        self.thickness_slider.setRange(1, 20)
        self.thickness_slider.setValue(2)
        self.thickness_slider.valueChanged.connect(self.set_thickness)
        self.toolbar.addWidget(self.thickness_slider)

        self.toolbar.addSeparator()

        self.font_size_label = QLabel("字号: 16")
        self.toolbar.addWidget(self.font_size_label)

        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(8, 72)
        self.font_size_slider.setValue(16)
        self.font_size_slider.valueChanged.connect(self.set_font_size)
        self.toolbar.addWidget(self.font_size_slider)

        self.bold_action = QAction("B", self)
        self.bold_action.setCheckable(True)
        self.bold_action.toggled.connect(self.set_bold_style)
        font = self.bold_action.font()
        font.setBold(True)
        self.bold_action.setFont(font)
        self.toolbar.addAction(self.bold_action)

        self.toolbar.addSeparator()

        self.save_action = QAction("保存", self)
        self.save_action.triggered.connect(self.save_annotations)
        self.toolbar.addAction(self.save_action)
        
        self.preview_action = QAction("🔍 预览效果", self)
        self.preview_action.triggered.connect(self.preview_annotated_image)
        self.toolbar.addAction(self.preview_action)

        self.image_label = AnnotationLabel() # 使用我们自定义的Label
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid black;")

        # 底部导航和返回按钮
        navigation_layout = QHBoxLayout()
        self.prev_button = QPushButton("<< 上一张")
        self.delete_current_button = QPushButton("🗑️ 删除当前图片")
        self.back_button = QPushButton("返回列表")
        self.next_button = QPushButton("下一张 >>")
        
        # 确保按钮可以接收焦点和事件
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.delete_current_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.back_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.next_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 设置删除按钮样式（红色警告色）
        self.delete_current_button.setStyleSheet("QPushButton { background-color: #ffebee; color: #c62828; border: 1px solid #c62828; }")
        
        navigation_layout.addWidget(self.prev_button)
        navigation_layout.addWidget(self.delete_current_button)
        navigation_layout.addStretch()
        navigation_layout.addWidget(self.back_button)
        navigation_layout.addStretch()
        navigation_layout.addWidget(self.next_button)

        self.layout.addLayout(navigation_layout)
        self.layout.addWidget(self.image_label, 1)
    
    def delete_current_image(self):
        """删除当前正在标注的图片"""
        if not hasattr(self, 'original_image_path') or not hasattr(self, 'annotated_image_path'):
            return
        
        # 从路径中获取图片文件名
        image_name = os.path.basename(self.original_image_path)
        
        # 确认删除对话框
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            '确认删除', 
            f'确定要删除图片 "{image_name}" 吗？\n\n此操作将删除：\n- 原始图片\n- 标注图片（如果存在）\n- 标注数据（如果存在）\n\n此操作不可撤销！',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 删除原始图片
                if os.path.exists(self.original_image_path):
                    os.remove(self.original_image_path)
                    print(f"🗑️ [DEBUG] Deleted original image: {self.original_image_path}")
                
                # 删除标注图片
                if os.path.exists(self.annotated_image_path):
                    os.remove(self.annotated_image_path)
                    print(f"🗑️ [DEBUG] Deleted annotated image: {self.annotated_image_path}")
                
                # 删除标注数据JSON文件
                json_path = os.path.splitext(self.annotated_image_path)[0] + ".json"
                if os.path.exists(json_path):
                    os.remove(json_path)
                    print(f"🗑️ [DEBUG] Deleted annotation data: {json_path}")
                
                print(f"✅ [DEBUG] Image '{image_name}' deleted successfully from annotation view")
                
                # 通知主窗口切换到下一张图片
                # 通过QApplication获取主窗口实例
                app = QApplication.instance()
                for widget in app.topLevelWidgets():
                    if isinstance(widget, MainWindow):
                        widget.switch_to_next_after_delete()
                        break
                
            except Exception as e:
                print(f"❌ [ERROR] Failed to delete image '{image_name}': {e}")
                QMessageBox.critical(self, "删除失败", f"删除图片时发生错误：{e}")

    def set_shape_type(self, shape_type):
        self.image_label.set_shape_type(shape_type)
        self.rect_action.setChecked(shape_type == 'rectangle')
        self.poly_action.setChecked(shape_type == 'polygon')
        self.text_action.setChecked(shape_type == 'text')

    def select_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.image_label.set_color(color)

    def set_thickness(self, value):
        self.image_label.set_thickness(value)
        self.thickness_label.setText(f"粗细: {value}")

    def set_font_size(self, value):
        self.image_label.set_font_size(value)
        self.font_size_label.setText(f"字号: {value}")

    def set_bold_style(self, checked):
        self.image_label.set_bold(checked)

    def debug_action_click(self, action_name, callback):
        print(f"🎯 [DEBUG] Action '{action_name}' triggered!")
        try:
            callback()
            print(f"✅ [DEBUG] Action '{action_name}' executed successfully")
        except Exception as e:
            print(f"❌ [DEBUG] Action '{action_name}' failed: {e}")

    def undo_last_annotation(self):
        self.image_label.undo()

    def set_image(self, original_path, annotated_path):
        print(f"🚀 [DEBUG] set_image called")
        print(f"🚀 [DEBUG] Original path: {original_path}")
        print(f"🚀 [DEBUG] Annotated path: {annotated_path}")
        
        self.original_image_path = original_path
        self.annotated_image_path = annotated_path
        
        # 检查是否存在JSON标注文件
        json_path = os.path.join(os.path.dirname(annotated_path), os.path.splitext(os.path.basename(annotated_path))[0] + ".json")
        if os.path.exists(json_path):
            print(f"📝 [DEBUG] Found annotation JSON file: {json_path}")
        
        # 准备标注文件路径
        if not os.path.exists(self.annotated_image_path):
            print(f"📁 [DEBUG] Annotated file doesn't exist, copying from original")
            shutil.copy(self.original_image_path, self.annotated_image_path)
        
        # 进入编辑模式时，始终加载原始图片以避免重影
        print(f"📷 [DEBUG] Loading pixmap from original: {self.original_image_path}")
        pixmap = QPixmap(self.original_image_path)
        print(f"📷 [DEBUG] Loaded pixmap - null: {pixmap.isNull()}, size: {pixmap.width()}x{pixmap.height()}")
        
        # 进入图片时总是允许编辑模式，加载JSON数据进行编辑
        self.image_label.is_displaying_saved_annotations = False
        print(f"🎨 [DEBUG] Set to editing mode - can see and edit annotations from JSON")
        
        # 加载现有标注数据到内存中供编辑
        self.image_label.shapes = self.load_annotation_data()
        print(f"📊 [DEBUG] Loaded {len(self.image_label.shapes)} annotations from JSON for editing")
        
        # 将原始pixmap传递给label，由label自己管理缩放
        print(f"📤 [DEBUG] Calling image_label.set_new_pixmap")
        self.image_label.set_new_pixmap(pixmap)
        print(f"📤 [DEBUG] set_new_pixmap call completed")
        
    def save_annotations(self):
        # 1. 保存标注元数据到 JSON 文件 (现在存的是真实坐标)
        self.save_annotation_data()

        # 2. 将标注绘制到图片上并保存 (使用真实坐标)
        # 直接从label获取原始pixmap进行绘制
        pixmap_to_save = self.image_label._pixmap.copy()
        painter = QPainter(pixmap_to_save)
        
        # 为了在原始图片上绘制，我们需要一个特殊的paintEvent调用
        # 这里我们模拟一个临时的painter，它不需要转换坐标
        for shape in self.image_label.shapes:
            pen = QPen(shape["color"], shape["thickness"] if "thickness" in shape else 1, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            if shape["type"] == "rectangle":
                rect = self.image_label.get_rect_from_points(shape["points"][0], shape["points"][1])
                painter.drawRect(*rect)
            elif shape["type"] == "polygon":
                painter.drawPolygon(shape["points"])
            elif shape["type"] == "text":
                font = QFont()
                font.setPointSize(shape["font_size"])
                font.setBold(shape.get("bold", False))
                painter.setFont(font)
                painter.drawText(shape["pos"].toPoint(), shape["text"])

        painter.end() 
        pixmap_to_save.save(self.annotated_image_path)
        
        # 保持标注页面始终显示JSON数据（可编辑状态）
        # 不改变当前显示，用户可以继续编辑
        print(f"🎨 [DEBUG] 保持编辑模式，用户可以继续标注或通过预览按钮查看效果")
        
        print(f"标注已保存到 {self.annotated_image_path}")
        
        # 刷新任务列表中的标注状态显示
        if hasattr(self.parent(), 'current_task_widget') and self.parent().current_task_widget:
            self.parent().current_task_widget.load_images()
            
    def preview_annotated_image(self):
        """预览标注后的图片效果"""
        if not hasattr(self, 'annotated_image_path'):
            QMessageBox.information(self, "提示", "请先保存标注后再预览！")
            return
            
        # 检查是否存在已保存的标注图片
        if not os.path.exists(self.annotated_image_path):
            QMessageBox.information(self, "提示", "请先保存标注后再预览！")
            return
            
        # 创建预览对话框
        from PyQt6.QtWidgets import QDialog, QScrollArea
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("标注效果预览")
        preview_dialog.setModal(True)
        preview_dialog.resize(800, 600)
        
        # 创建布局
        layout = QVBoxLayout(preview_dialog)
        
        # 添加说明标签
        info_label = QLabel("📸 预览：绘制了标注信息的最终图片效果")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("padding: 10px; background-color: #e3f2fd; border-radius: 5px; color: #1976d2;")
        layout.addWidget(info_label)
        
        # 创建滚动区域显示图片
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 加载并显示标注后的图片
        preview_label = QLabel()
        preview_pixmap = QPixmap(self.annotated_image_path)
        
        # 如果图片过大，进行缩放
        if preview_pixmap.width() > 700 or preview_pixmap.height() > 500:
            preview_pixmap = preview_pixmap.scaled(700, 500, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        preview_label.setPixmap(preview_pixmap)
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setWidget(preview_label)
        layout.addWidget(scroll_area)
        
        # 添加关闭按钮
        close_button = QPushButton("关闭预览")
        close_button.clicked.connect(preview_dialog.close)
        layout.addWidget(close_button)
        
        print(f"🔍 [DEBUG] 预览标注图片: {self.annotated_image_path}")
        preview_dialog.exec()

    def reset_annotations(self):
        # 1. 清空内存中的标注
        self.image_label.shapes = []
        self.image_label.current_polygon_points = []
        
        # 2. 从原始图片覆盖已标注的图片
        shutil.copy(self.original_image_path, self.annotated_image_path)
        
        # 3. 删除JSON元数据文件
        json_path = os.path.splitext(self.annotated_image_path)[0] + ".json"
        if os.path.exists(json_path):
            os.remove(json_path)

        # 4. 重新加载并更新显示
        pixmap = QPixmap(self.annotated_image_path)
        # 重置后不再是已保存标注状态
        self.image_label.is_displaying_saved_annotations = False
        self.image_label.set_new_pixmap(pixmap)
        print("标注已重置。")
        
        # 刷新任务列表中的标注状态显示
        if hasattr(self.parent(), 'current_task_widget') and self.parent().current_task_widget:
            self.parent().current_task_widget.load_images()

    def get_json_path(self):
        return os.path.splitext(self.annotated_image_path)[0] + ".json"

    def save_annotation_data(self):
        json_path = self.get_json_path()
        # 需要将 PyQt 对象（如 QPoint, QColor）转换为可序列化的格式
        serializable_shapes = []
        for shape in self.image_label.shapes:
            s_shape = shape.copy()
            
            # 修复 KeyError: 'points'
            if s_shape.get("points"): # Handles both rectangle and polygon
                s_shape["points"] = [(p.x(), p.y()) for p in s_shape["points"]]
            
            if s_shape.get("pos"): # Handles text
                s_shape["pos"] = (s_shape["pos"].x(), s_shape["pos"].y())

            # 修复：只在颜色是QColor对象时才调用 .name()
            if isinstance(s_shape.get("color"), QColor):
                s_shape["color"] = s_shape["color"].name()
            serializable_shapes.append(s_shape)

        with open(json_path, 'w') as f:
            json.dump(serializable_shapes, f, indent=4)
            
    def load_annotation_data(self):
        json_path = self.get_json_path()
        if not os.path.exists(json_path):
            return []
            
        with open(json_path, 'r') as f:
            try:
                serializable_shapes = json.load(f)
            except json.JSONDecodeError:
                print(f"警告：标注文件 {json_path} 已损坏或为空，将忽略现有标注。")
                return []
        
        # 将序列化的数据转换回 PyQt 对象
        shapes = []
        for s_shape in serializable_shapes:
            shape = s_shape.copy()
            if shape["type"] == "rectangle":
                # Stored as tuple of QPointF, need to convert back
                shape["points"] = (QPointF(shape["points"][0][0], shape["points"][0][1]), QPointF(shape["points"][1][0], shape["points"][1][1]))
            elif shape["type"] == "polygon":
                shape["points"] = [QPointF(p[0], p[1]) for p in shape["points"]]
            elif shape["type"] == "text":
                shape["pos"] = QPointF(shape["pos"][0], shape["pos"][1])

            shape["color"] = QColor(shape["color"])
            shapes.append(shape)
        return shapes


class TaskWidget(QWidget):
    """显示一个任务的图片列表和操作的控件"""
    def __init__(self, task_name, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.layout = QVBoxLayout(self)

        self.task_label = QLabel(f"当前任务: {task_name}")
        self.task_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.task_label)

        self.image_list_widget = QListWidget()
        self.image_list_widget.itemDoubleClicked.connect(self.parent().open_annotation_view)
        self.layout.addWidget(self.image_list_widget)
        
        # 删除图片按钮
        self.delete_image_button = QPushButton("删除选中图片")
        self.delete_image_button.clicked.connect(self.delete_selected_image)
        self.delete_image_button.setEnabled(False)  # 默认禁用
        self.layout.addWidget(self.delete_image_button)
        
        # 启用图片选中状态监听
        self.image_list_widget.itemSelectionChanged.connect(self.on_image_selection_changed)
        
        self.synthesize_video_button = QPushButton("合成视频")
        self.synthesize_video_button.clicked.connect(self.parent().synthesize_video)
        self.layout.addWidget(self.synthesize_video_button)

        self.back_to_tasks_button = QPushButton("返回任务列表")
        self.back_to_tasks_button.clicked.connect(self.parent().show_task_selection)
        self.layout.addWidget(self.back_to_tasks_button)

        self.load_images()

    def load_images(self):
        self.image_list_widget.clear()
        base_task_dir = os.path.join("data", self.task_name)
        frames_dir = os.path.join(base_task_dir, "original_frames")
        annotated_frames_dir = os.path.join(base_task_dir, "annotated_frames")
        
        if os.path.exists(frames_dir):
            images = [f for f in sorted(os.listdir(frames_dir)) if f.endswith(".png")]
            for image_name in images:
                # 检查是否已标注：查看是否存在对应的JSON文件或已修改的图片
                annotated_image_path = os.path.join(annotated_frames_dir, image_name)
                json_path = os.path.join(annotated_frames_dir, os.path.splitext(image_name)[0] + ".json")
                
                is_annotated = False
                if os.path.exists(json_path):
                    # 如果有JSON文件，说明已标注
                    is_annotated = True
                elif os.path.exists(annotated_image_path):
                    # 如果标注图片存在，比较文件修改时间
                    original_path = os.path.join(frames_dir, image_name)
                    if os.path.getmtime(annotated_image_path) > os.path.getmtime(original_path):
                        is_annotated = True
                
                # 根据标注状态添加标记
                display_name = f"✅ {image_name}" if is_annotated else f"⚪ {image_name}"
                item = QListWidgetItem(display_name)
                item.setData(Qt.ItemDataRole.UserRole, image_name)  # 保存原始文件名
                self.image_list_widget.addItem(item)
    
    def on_image_selection_changed(self):
        # 控制删除按钮的启用状态
        has_selection = bool(self.image_list_widget.currentItem())
        self.delete_image_button.setEnabled(has_selection)
    
    def delete_selected_image(self):
        current_item = self.image_list_widget.currentItem()
        if not current_item:
            return
        
        # 获取原始图片文件名
        image_name = current_item.data(Qt.ItemDataRole.UserRole) or current_item.text()
        # 移除状态标记（如果存在）
        if image_name.startswith("✅ ") or image_name.startswith("⚪ "):
            image_name = image_name[2:]
        
        # 确认删除对话框
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            '确认删除', 
            f'确定要删除图片 "{image_name}" 吗？\n\n此操作将删除：\n- 原始图片\n- 标注图片（如果存在）\n- 标注数据（如果存在）\n\n此操作不可撤销！',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                base_task_dir = os.path.join("data", self.task_name)
                frames_dir = os.path.join(base_task_dir, "original_frames")
                annotated_frames_dir = os.path.join(base_task_dir, "annotated_frames")
                
                # 删除原始图片
                original_path = os.path.join(frames_dir, image_name)
                if os.path.exists(original_path):
                    os.remove(original_path)
                    print(f"🗑️ [DEBUG] Deleted original image: {original_path}")
                
                # 删除标注图片
                annotated_path = os.path.join(annotated_frames_dir, image_name)
                if os.path.exists(annotated_path):
                    os.remove(annotated_path)
                    print(f"🗑️ [DEBUG] Deleted annotated image: {annotated_path}")
                
                # 删除标注数据JSON文件
                json_path = os.path.join(annotated_frames_dir, os.path.splitext(image_name)[0] + ".json")
                if os.path.exists(json_path):
                    os.remove(json_path)
                    print(f"🗑️ [DEBUG] Deleted annotation data: {json_path}")
                
                # 从图片列表中移除
                self.image_list_widget.takeItem(self.image_list_widget.row(current_item))
                
                print(f"✅ [DEBUG] Image '{image_name}' deleted successfully")
                QMessageBox.information(self, "删除成功", f"图片 '{image_name}' 已成功删除！")
                
            except Exception as e:
                print(f"❌ [ERROR] Failed to delete image '{image_name}': {e}")
                QMessageBox.critical(self, "删除失败", f"删除图片时发生错误：{e}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频标注工具")
        self.setGeometry(100, 100, 1200, 800)

        # 使用 QStackedWidget 来切换主界面和标注界面
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # 0: 任务选择界面
        self.task_selection_widget = QWidget()
        self.task_selection_layout = QVBoxLayout(self.task_selection_widget)
        
        # 为任务选择界面添加标题
        title_label = QLabel("任务列表")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title_label.font()
        font.setPointSize(24)
        font.setBold(True)
        title_label.setFont(font)
        self.task_selection_layout.addWidget(title_label)

        self.new_task_button = QPushButton("创建新任务")
        self.new_task_button.clicked.connect(self.create_new_task)
        self.task_selection_layout.addWidget(self.new_task_button)

        self.task_list_widget = QListWidget()
        self.task_list_widget.itemClicked.connect(self.open_task)
        self.task_selection_layout.addWidget(self.task_list_widget)
        
        # 删除任务按钮
        self.delete_task_button = QPushButton("删除选中任务")
        self.delete_task_button.clicked.connect(self.delete_selected_task)
        self.delete_task_button.setEnabled(False)  # 默认禁用
        self.task_selection_layout.addWidget(self.delete_task_button)
        
        # 启用任务选中状态监听
        self.task_list_widget.itemSelectionChanged.connect(self.on_task_selection_changed)
        
        # 1: 任务详情 (图片列表)
        # 这个会被动态创建和替换
        self.task_widget = QWidget()
        self.current_task_widget = None # 增加一个引用

        # 2: 标注界面
        self.annotation_widget = AnnotationWidget()
        self.annotation_widget.back_button.clicked.connect(lambda: self.debug_button_click("back", self.show_task_view))
        self.annotation_widget.prev_button.clicked.connect(lambda: self.debug_button_click("prev", self.show_previous_image))
        self.annotation_widget.delete_current_button.clicked.connect(self.annotation_widget.delete_current_image)
        self.annotation_widget.next_button.clicked.connect(lambda: self.debug_button_click("next", self.show_next_image))

        self.stacked_widget.addWidget(self.task_selection_widget)
        self.stacked_widget.addWidget(self.task_widget)
        self.stacked_widget.addWidget(self.annotation_widget)

        self.current_task_name = None
        self.load_tasks()

    def debug_button_click(self, button_name, callback):
        print(f"🔘 [DEBUG] Button '{button_name}' clicked!")
        try:
            callback()
            print(f"✅ [DEBUG] Button '{button_name}' callback executed successfully")
        except Exception as e:
            print(f"❌ [DEBUG] Button '{button_name}' callback failed: {e}")

    def get_tasks_file(self):
        return os.path.join("data", "tasks.json")

    def load_tasks(self):
        self.task_list_widget.clear()
        tasks_file = self.get_tasks_file()
        if os.path.exists(tasks_file):
            with open(tasks_file, 'r') as f:
                tasks = json.load(f)
                for task_name in tasks:
                    # 检查是否已合成视频
                    task_dir = os.path.join("data", task_name)
                    has_video = False
                    
                    # 1. 检查任务目录下是否有mp4文件
                    if os.path.exists(task_dir):
                        for file in os.listdir(task_dir):
                            if file.endswith('.mp4'):
                                has_video = True
                                break
                    
                    # 2. 检查根目录下是否有对应的标注视频文件
                    if not has_video:
                        annotated_video_path = f"{task_name}_annotated.mp4"
                        if os.path.exists(annotated_video_path):
                            has_video = True
                            print(f"🎬 [DEBUG] Found video file for task '{task_name}': {annotated_video_path}")
                    
                    # 根据视频状态添加标记
                    display_name = f"🎬 {task_name}" if has_video else f"📁 {task_name}"
                    item = QListWidgetItem(display_name)
                    item.setData(Qt.ItemDataRole.UserRole, task_name)  # 保存原始任务名
                    self.task_list_widget.addItem(item)
    
    def save_tasks(self):
        tasks = []
        for i in range(self.task_list_widget.count()):
            item = self.task_list_widget.item(i)
            # 保存原始任务名，不包含状态标记
            task_name = item.data(Qt.ItemDataRole.UserRole) or item.text()
            tasks.append(task_name)
        
        tasks_file = self.get_tasks_file()
        os.makedirs(os.path.dirname(tasks_file), exist_ok=True)
        with open(tasks_file, 'w') as f:
            json.dump(tasks, f, indent=4)

    def create_new_task(self):
        dialog = NewTaskDialog(self)
        if dialog.exec():
            task_info = dialog.get_task_info()
            self.current_task_name = task_info["task_name"]
            video_path = task_info["video_path"]
            frame_interval = task_info["frame_interval"]

            if not self.current_task_name or not video_path:
                print("错误：任务名称和视频路径不能为空。")
                self.current_task_name = None
                return

            base_task_dir = os.path.join("data", self.current_task_name)
            original_frames_dir = os.path.join(base_task_dir, "original_frames")
            annotated_frames_dir = os.path.join(base_task_dir, "annotated_frames")

            os.makedirs(original_frames_dir, exist_ok=True)
            os.makedirs(annotated_frames_dir, exist_ok=True)

            print(f"开始抽帧，请稍候...")
            extract_frames(video_path, original_frames_dir, frame_interval)
            print("抽帧完成。")

            # 将新任务添加到列表并保存
            if self.task_list_widget.findItems(self.current_task_name, Qt.MatchFlag.MatchExactly):
                pass # 任务已存在
            else:
                self.task_list_widget.addItem(self.current_task_name)
            self.save_tasks()
            
            self.open_task(self.task_list_widget.findItems(self.current_task_name, Qt.MatchFlag.MatchExactly)[0])
    
    def open_task(self, item):
        # 从 UserRole 获取原始任务名，忽略状态标记
        self.current_task_name = item.data(Qt.ItemDataRole.UserRole) or item.text()
        # 替换掉旧的 task_widget
        if self.current_task_widget:
            self.stacked_widget.removeWidget(self.current_task_widget)
        
        self.current_task_widget = TaskWidget(self.current_task_name, self)
        self.stacked_widget.insertWidget(1, self.current_task_widget)
        self.stacked_widget.setCurrentIndex(1)

    def open_annotation_view(self, item):
        # 从 UserRole 获取原始文件名，忽略标注状态标记
        image_name = item.data(Qt.ItemDataRole.UserRole) or item.text()
        print(f"🚪 [DEBUG] open_annotation_view called with item: {item.text()}, real name: {image_name}")
        
        if not self.current_task_widget:
            print(f"❌ [DEBUG] No current_task_widget, returning")
            return
            
        # 更新列表中的选中项
        list_widget = self.current_task_widget.image_list_widget
        list_widget.setCurrentItem(item)
        if self.current_task_name:
            base_task_dir = os.path.join("data", self.current_task_name)
            original_path = os.path.join(base_task_dir, "original_frames", image_name)
            annotated_path = os.path.join(base_task_dir, "annotated_frames", image_name)
            
            print(f"🔀 [DEBUG] Before switching - current stack index: {self.stacked_widget.currentIndex()}")
            print(f"🔀 [DEBUG] Stack widget count: {self.stacked_widget.count()}")
            
            # 详细检查每个控件
            for i in range(self.stacked_widget.count()):
                widget = self.stacked_widget.widget(i)
                widget_name = widget.__class__.__name__
                if hasattr(widget, 'task_name'):
                    widget_name += f"({widget.task_name})"
                print(f"🔀 [DEBUG] Stack index {i}: {widget_name}, visible: {widget.isVisible()}")
            
            print(f"🔀 [DEBUG] Annotation widget visible: {self.annotation_widget.isVisible()}")
            print(f"🔀 [DEBUG] Annotation widget in stack at index: {self.stacked_widget.indexOf(self.annotation_widget)}")
            
            self.annotation_widget.set_image(original_path, annotated_path)
            
            annotation_index = self.stacked_widget.indexOf(self.annotation_widget)
            print(f"🔀 [DEBUG] Switching to annotation view (index {annotation_index})")
            self.stacked_widget.setCurrentIndex(annotation_index)
            
            print(f"🔀 [DEBUG] After switching - current stack index: {self.stacked_widget.currentIndex()}")
            print(f"🔀 [DEBUG] Annotation widget visible after switch: {self.annotation_widget.isVisible()}")
            print(f"🔀 [DEBUG] Current widget class: {self.stacked_widget.currentWidget().__class__.__name__}")
            
            # 强制更新以确保显示
            self.stacked_widget.update()
            self.annotation_widget.update()

    def show_previous_image(self):
        if not self.current_task_widget:
            return
        
        list_widget = self.current_task_widget.image_list_widget
        current_row = list_widget.currentRow()
        if current_row > 0:
            item = list_widget.item(current_row - 1)
            self.open_annotation_view(item)

    def show_next_image(self):
        if not self.current_task_widget:
            return
        
        list_widget = self.current_task_widget.image_list_widget
        current_row = list_widget.currentRow()
        if current_row < list_widget.count() - 1:
            item = list_widget.item(current_row + 1)
            self.open_annotation_view(item)
    
    def switch_to_next_after_delete(self):
        """删除当前图片后，智能切换到下一张图片"""
        if not self.current_task_widget:
            return
        
        # 重新加载图片列表以反映删除操作
        current_image_name = None
        if hasattr(self.annotation_widget, 'original_image_path'):
            current_image_name = os.path.basename(self.annotation_widget.original_image_path)
        
        self.current_task_widget.load_images()
        list_widget = self.current_task_widget.image_list_widget
        
        # 如果没有图片了，返回任务列表
        if list_widget.count() == 0:
            print("📂 [DEBUG] No images left, returning to task list")
            QMessageBox.information(self, "提示", "该任务中已没有图片，返回任务列表。")
            self.show_task_view()
            return
        
        # 尝试找到一个合适的图片来显示
        target_item = None
        
        # 首先尝试找到下一张图片（基于文件名排序）
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item_name = item.data(Qt.ItemDataRole.UserRole) or item.text()
            # 移除状态标记
            if item_name.startswith("✅ ") or item_name.startswith("⚪ "):
                item_name = item_name[2:]
            
            if current_image_name and item_name > current_image_name:
                target_item = item
                break
        
        # 如果没有找到下一张，选择第一张
        if not target_item and list_widget.count() > 0:
            target_item = list_widget.item(0)
        
        # 切换到目标图片
        if target_item:
            print(f"📸 [DEBUG] Switching to image after delete: {target_item.text()}")
            self.open_annotation_view(target_item)
        else:
            # 如果还是没有，返回任务列表
            print("📂 [DEBUG] No suitable image found, returning to task list")
            self.show_task_view()

    def synthesize_video(self):
        if self.current_task_name:
            base_task_dir = os.path.join("data", self.current_task_name)
            annotated_frames_dir = os.path.join(base_task_dir, "annotated_frames")

            if not os.path.exists(annotated_frames_dir) or not os.listdir(annotated_frames_dir):
                print("错误：找不到已标注的图片，无法合成视频。")
                return

            # 弹出对话框让用户选择保存路径和设置FPS
            save_path, _ = QFileDialog.getSaveFileName(self, "保存视频", f"{self.current_task_name}_annotated.mp4", "MP4视频 (*.mp4)")
            
            if save_path:
                # 这里可以再弹出一个对话框来获取FPS，为简化，我们先用一个默认值
                fps = 30 
                print(f"开始合成视频，请稍候...")
                create_video(annotated_frames_dir, save_path, fps)
                QMessageBox.information(self, "成功", "视频合成完毕！")
                print("视频合成完毕。")
                
                # 刷新任务列表中的视频合成状态显示
                self.load_tasks()

    def on_task_selection_changed(self):
        # 控制删除按钮的启用状态
        has_selection = bool(self.task_list_widget.currentItem())
        self.delete_task_button.setEnabled(has_selection)
    
    def delete_selected_task(self):
        current_item = self.task_list_widget.currentItem()
        if not current_item:
            return
        
        # 获取原始任务名
        task_name = current_item.data(Qt.ItemDataRole.UserRole) or current_item.text()
        # 移除状态标记（如果存在）
        if task_name.startswith("🎬 ") or task_name.startswith("📁 "):
            task_name = task_name[2:]
        
        # 确认删除对话框
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            '确认删除', 
            f'确定要删除任务 "{task_name}" 吗？\n\n此操作将删除：\n- 所有原始图片\n- 所有标注图片\n- 所有标注数据\n- 相关的视频文件\n\n此操作不可撤销！',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                import shutil
                # 删除整个任务目录
                task_dir = os.path.join("data", task_name)
                if os.path.exists(task_dir):
                    shutil.rmtree(task_dir)
                    print(f"🗑️ [DEBUG] Deleted task directory: {task_dir}")
                
                # 删除可能存在的视频文件（在根目录）
                video_file = f"{task_name}_annotated.mp4"
                if os.path.exists(video_file):
                    os.remove(video_file)
                    print(f"🗑️ [DEBUG] Deleted video file: {video_file}")
                
                # 从任务列表中移除
                self.task_list_widget.takeItem(self.task_list_widget.row(current_item))
                
                # 更新任务列表文件
                self.save_tasks()
                
                print(f"✅ [DEBUG] Task '{task_name}' deleted successfully")
                QMessageBox.information(self, "删除成功", f"任务 '{task_name}' 已成功删除！")
                
            except Exception as e:
                print(f"❌ [ERROR] Failed to delete task '{task_name}': {e}")
                QMessageBox.critical(self, "删除失败", f"删除任务时发生错误：{e}")

    def show_task_selection(self):
        # 返回任务列表时刷新任务状态（包括视频合成状态）
        self.load_tasks()
        self.stacked_widget.setCurrentIndex(0)

    def show_task_view(self):
        self.stacked_widget.setCurrentIndex(1)
        # 返回图片列表时刷新标注状态显示
        if self.current_task_widget:
            self.current_task_widget.load_images()


if __name__ == "__main__":
    # 确保在虚拟环境中运行
    if "VIRTUAL_ENV" not in os.environ:
         print("警告：请在激活的Python虚拟环境中运行此应用。")
         # sys.exit(1) # 可以选择在没有虚拟环境时退出

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
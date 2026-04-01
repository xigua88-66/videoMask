import os
import json

def extract_frames(video_path, output_dir, interval):
    import cv2
    """
    将视频按指定间隔抽帧为图片。

    :param video_path: 视频文件路径
    :param output_dir: 图片输出目录
    :param interval: 抽帧间隔（每隔多少帧抽取一张）
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: 无法打开视频文件 {video_path}")
        return

    frame_count = 0
    saved_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % interval == 0:
            image_path = os.path.join(output_dir, f"frame_{saved_count:06d}.png")
            cv2.imwrite(image_path, frame)
            saved_count += 1
        
        frame_count += 1

    cap.release()
    print(f"视频抽帧完成，共保存 {saved_count} 张图片。")

def probe_video(video_path):
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return {
        "fps": fps,
        "total_frames": total_frames,
    }

def create_video(image_dir, output_video_path, fps, original_video_path=None, frame_interval=1):
    import cv2
    import numpy as np
    try:
        from PIL import Image, ImageDraw, ImageFont
        pil_available = True
    except Exception:
        pil_available = False
    """
    将一系列图片合成为视频。

    :param image_dir: 图片所在目录
    :param output_video_path: 输出视频的路径
    :param fps: 视频的帧率
    """
    def _hex_to_bgr(color_hex):
        if not isinstance(color_hex, str):
            return (0, 0, 255)
        text = color_hex.lstrip("#")
        if len(text) != 6:
            return (0, 0, 255)
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
        return (b, g, r)

    def _to_point(point_like):
        return int(point_like[0]), int(point_like[1])

    def _draw_shapes(frame, shapes):
        pil_img = None
        pil_draw = None
        font_cache = {}
        font_path = None
        if pil_available:
            font_candidates = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
            ]
            for candidate in font_candidates:
                if os.path.exists(candidate):
                    font_path = candidate
                    break

        def _draw_text(text, x, y, color_bgr, size=16, bold=False):
            nonlocal pil_img, pil_draw
            if not text:
                return
            x = int(x)
            y = int(y)
            if font_path:
                if pil_img is None:
                    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    pil_draw = ImageDraw.Draw(pil_img)
                font_key = (size, bool(bold))
                if font_key not in font_cache:
                    font_cache[font_key] = ImageFont.truetype(font_path, size=max(12, int(size)))
                rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
                pil_draw.text((x, y), text, font=font_cache[font_key], fill=rgb)
            else:
                cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_bgr, 2, cv2.LINE_AA)

        for shape in shapes:
            color = _hex_to_bgr(shape.get("color", "#ff0000"))
            thickness = int(shape.get("thickness", 2))
            shape_type = shape.get("type")

            if shape_type == "rectangle":
                p1 = _to_point(shape["points"][0])
                p2 = _to_point(shape["points"][1])
                cv2.rectangle(frame, p1, p2, color, thickness)
                label_text = (shape.get("label_text") or "").strip()
                if label_text:
                    x = min(p1[0], p2[0])
                    y = min(p1[1], p2[1]) - 8
                    _draw_text(label_text, x, y, color, size=int(shape.get("label_font_size", 16)), bold=bool(shape.get("label_bold", False)))
            elif shape_type == "polygon":
                pts = np.array([_to_point(p) for p in shape["points"]], dtype=np.int32)
                if len(pts) >= 2:
                    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=thickness)
                label_text = (shape.get("label_text") or "").strip()
                if label_text and len(pts) > 0:
                    x = int(np.min(pts[:, 0]))
                    y = int(np.min(pts[:, 1])) - 8
                    _draw_text(label_text, x, y, color, size=int(shape.get("label_font_size", 16)), bold=bool(shape.get("label_bold", False)))
            elif shape_type == "text":
                pos = _to_point(shape.get("pos", (0, 0)))
                text = (shape.get("text") or "").strip()
                if text:
                    _draw_text(text, pos[0], pos[1], color, size=int(shape.get("font_size", 16)), bold=bool(shape.get("bold", False)))

        if pil_img is not None:
            frame[:, :, :] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    if original_video_path and os.path.exists(original_video_path):
        cap = cv2.VideoCapture(original_video_path)
        if not cap.isOpened():
            print(f"Error: 无法打开原始视频文件 {original_video_path}")
            return

        source_fps = cap.get(cv2.CAP_PROP_FPS) or fps or 30
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 收集每个抽样帧对应的标注数据
        shape_by_sample_idx = {}
        for name in sorted(os.listdir(image_dir)):
            if not name.endswith(".json"):
                continue
            stem = os.path.splitext(name)[0]
            if not stem.startswith("frame_"):
                continue
            try:
                sample_idx = int(stem.split("_")[1])
            except Exception:
                continue
            json_path = os.path.join(image_dir, name)
            try:
                with open(json_path, "r") as f:
                    shape_by_sample_idx[sample_idx] = json.load(f)
            except Exception:
                shape_by_sample_idx[sample_idx] = []

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(output_video_path, fourcc, source_fps, (width, height))

        last_shapes = []
        frame_idx = 0
        step = max(1, int(frame_interval))
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            sample_idx = frame_idx // step
            if sample_idx in shape_by_sample_idx:
                last_shapes = shape_by_sample_idx[sample_idx]

            if last_shapes:
                _draw_shapes(frame, last_shapes)

            video.write(frame)
            frame_idx += 1

        cap.release()
        video.release()
        print(f"视频合成完成，已保存至 {output_video_path}。")
        return

    # 回退：没有原视频时，按标注帧图片序列合成
    images = [img for img in sorted(os.listdir(image_dir)) if img.endswith(".png")]
    if not images:
        print("目录下没有找到图片文件。")
        return
    frame = cv2.imread(os.path.join(image_dir, images[0]))
    height, width, _ = frame.shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))
    for image in images:
        img = cv2.imread(os.path.join(image_dir, image))
        if img is not None:
            video.write(img)
    video.release()
    print(f"视频合成完成，已保存至 {output_video_path}。")
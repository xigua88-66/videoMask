import cv2
import os

def extract_frames(video_path, output_dir, interval):
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

def create_video(image_dir, output_video_path, fps):
    """
    将一系列图片合成为视频。

    :param image_dir: 图片所在目录
    :param output_video_path: 输出视频的路径
    :param fps: 视频的帧率
    """
    images = [img for img in sorted(os.listdir(image_dir)) if img.endswith(".png")]
    if not images:
        print("目录下没有找到图片文件。")
        return

    frame = cv2.imread(os.path.join(image_dir, images[0]))
    height, width, layers = frame.shape

    # 视频编码器，mp4v 在 Mac 和 Windows 上有较好的兼容性
    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
    video = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    for image in images:
        video.write(cv2.imread(os.path.join(image_dir, image)))

    video.release()
    print(f"视频合成完成，已保存至 {output_video_path}。")
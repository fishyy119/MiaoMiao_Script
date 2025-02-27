import os
from PIL import Image
from tqdm import tqdm

# 当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 新文件夹路径
output_dir = os.path.join(current_dir, "processed_images")

# 如果输出目录不存在，创建它
if not os.path.exists(output_dir):
    os.makedirs(output_dir)


def split_and_move_image(image_path: str) -> None:
    try:
        with Image.open(image_path) as img:
            width, height = img.size

            # 检查图片尺寸
            if width >= 2000 or height >= 3000:
                # 计算左右分割的边界
                left_box = (0, 0, width // 2, height)
                right_box = (width // 2, 0, width, height)

                # 分割图片
                left_img = img.crop(left_box)
                right_img = img.crop(right_box)

                # 获取图片文件名和扩展名
                base_name, ext = os.path.splitext(os.path.basename(image_path))
                right_image_path = os.path.join(output_dir, f"{base_name}_left{ext}")  # 右半部分命名为 left
                left_image_path = os.path.join(output_dir, f"{base_name}_right{ext}")  # 左半部分命名为 right

                # 保存分割后的图片
                left_img.save(left_image_path, quality=100)  # 保存右半部分图片
                right_img.save(right_image_path, quality=100)  # 保存左半部分图片

                print(f"Processed {image_path} -> {left_image_path} and {right_image_path}")

                # 删除原始文件
                os.remove(image_path)
                print(f"Deleted original file {image_path}")

    except Exception as e:
        print(f"Error processing {image_path}: {e}")


# 获取所有图片文件
image_files = [f for f in os.listdir(current_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff"))]

# 使用 tqdm 显示进度条
for file_name in tqdm(image_files, desc="Processing images"):
    file_path = os.path.join(current_dir, file_name)
    split_and_move_image(file_path)

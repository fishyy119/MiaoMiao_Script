from PIL import Image
import os


def concat_images(image1_path: str, image2_path: str, output_path: str) -> None:
    img1 = Image.open(image1_path)
    img2 = Image.open(image2_path)

    # 获取图片尺寸
    width1, height1 = img1.size
    width2, height2 = img2.size

    # 创建新图片，宽度为两张图片宽度之和，高度为较高的图片高度
    new_image = Image.new("RGB", (width1 + width2, max(height1, height2)))

    # 粘贴图片
    new_image.paste(img2, (0, 0))  # 把第n+1项图片放在左边
    new_image.paste(img1, (width2, 0))  # 把第n项图片放在右边

    # 保存新图片
    new_image.save(output_path)


# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 获取当前目录下的所有图片文件
image_files = [
    os.path.join(current_dir, file)
    for file in os.listdir(current_dir)
    if file.split(".")[-1].lower() in {"png", "jpg", "jpeg", "bmp", "gif", "tiff"}
]

# 确保图片文件数量为偶数，如果是奇数则移除最后一个图片文件
if len(image_files) % 2 != 0:
    image_files = image_files[:-1]

# 创建存放拼接后图片的文件夹
output_dir = os.path.join(current_dir, "concatenated_images")
os.makedirs(output_dir, exist_ok=True)

# 拼接图片并保存
for i in range(0, len(image_files), 2):
    output_image = os.path.join(output_dir, f"output_image_{i//2 + 1}.png")
    concat_images(image_files[i], image_files[i + 1], output_image)

print(f"拼接后的图片保存在 {output_dir} 文件夹中。")

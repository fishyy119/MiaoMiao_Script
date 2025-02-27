import os
from PIL import Image

from typing import List


def create_output_directory(output_dir: str) -> None:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)


def get_sorted_png_files(input_dir: str) -> List[str]:
    files = [f for f in os.listdir(input_dir) if f.endswith(".png")]
    files.sort()
    return files


def concatenate_images(image1_path: str, image2_path: str, output_path: str) -> None:
    img1 = Image.open(image1_path)
    img2 = Image.open(image2_path)

    # Ensure the images have the same height
    if img1.size[1] != img2.size[1]:
        raise ValueError("Images do not have the same height")

    # Create a new image with width = img1.width + img2.width and height = img1.height
    new_img = Image.new("RGB", (img1.width + img2.width, img1.height))
    new_img.paste(img1, (0, 0))
    new_img.paste(img2, (img1.width, 0))

    new_img.save(output_path)


def main():
    input_dir = os.path.dirname(os.path.realpath(__file__))
    output_dir = os.path.join(input_dir, "output")

    create_output_directory(output_dir)
    files = get_sorted_png_files(input_dir)

    for i in range(0, len(files) - 1, 2):
        image1_path = os.path.join(input_dir, files[i])
        image2_path = os.path.join(input_dir, files[i + 1])
        output_path = os.path.join(output_dir, f"{str(i//2+1).zfill(4)}.png")

        concatenate_images(image1_path, image2_path, output_path)


if __name__ == "__main__":
    main()

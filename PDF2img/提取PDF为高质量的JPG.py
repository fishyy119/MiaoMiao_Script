import fitz  # type: ignore
import pymupdf  # type: ignore
import os
from PIL import Image
import io
from tqdm import tqdm


def extract_pages_as_images(pdf_path: str, output_folder: str, dpi: int = 300) -> None:
    # 打开PDF文件
    pdf_document = fitz.open(pdf_path)

    # 确保输出文件夹存在
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    page_count = len(pdf_document)

    # 遍历PDF中的每一页
    for page_number in tqdm(range(page_count), desc="Processing pages"):
        page = pdf_document.load_page(page_number)  # type: ignore

        # 设置渲染的DPI
        zoom_x = dpi / 72  # 72 DPI 是 PDF 默认的 DPI
        zoom_y = dpi / 72

        # 渲染页面为图像
        pix: pymupdf.Pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom_x, zoom_y))  # type: ignore
        img_bytes: bytes = pix.pil_tobytes(format="jpeg")  # type: ignore # 转换为 JPEG 格式的字节数据
        image_filename = f"page_{page_number + 1}.jpg"
        image_path = os.path.join(output_folder, image_filename)

        # 使用Pillow保存图像为 JPG 格式
        with Image.open(io.BytesIO(img_bytes)) as img:  # type: ignore
            img.save(image_path, format="JPEG", quality=100, optimize=True)

    pdf_document.close()
    print(f"提取完成，共提取了 {page_count} 页。")


if __name__ == "__main__":
    current_directory = os.path.dirname(os.path.abspath(__file__))
    pdf_files = [f for f in os.listdir(current_directory) if f.lower().endswith(".pdf")]

    for pdf_file in pdf_files:
        pdf_path = os.path.join(current_directory, pdf_file)
        output_folder = os.path.join(current_directory, f"{os.path.splitext(pdf_file)[0]}_pages")
        extract_pages_as_images(pdf_path, output_folder, dpi=300)

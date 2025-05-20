import os
import matplotlib.pyplot as plt
from PIL import Image
import pandas as pd


def select_points_and_calculate(image_folder, output_excel):
    data = []
    baseline_scale = None  # 新增比例系数存储

    # 获取所有图片文件
    image_files = [f for f in os.listdir(image_folder)
                   if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]

    for filename in image_files:
        filepath = os.path.join(image_folder, filename)

        try:
            # 打开图片并创建matplotlib窗口
            img = Image.open(filepath)
            plt.figure(figsize=(10, 6))
            plt.imshow(img)
            plt.title(f'点击选择两个点 ({filename})')

            # 获取用户输入坐标
            points = plt.ginput(2, timeout=0)
            plt.close()  # 关闭当前图片窗口

            if len(points) == 2:
                # 计算坐标和距离
                x1, y1 = points[0]
                x2, y2 = points[1]
                pixel_distance = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

                # 添加到数据列表
                data.append({
                    '图片名称': filename,
                    '点1_X': round(x1, 2),
                    '点1_Y': round(y1, 2),
                    '点2_X': round(x2, 2),
                    '点2_Y': round(y2, 2),
                    '像素距离': round(pixel_distance, 2)  # 修改字段名更清晰
                })

        except Exception as e:
            print(f"处理 {filename} 时出错: {str(e)}")
            continue

    # 计算实物距离
    if data:
        # 获取最后一条记录作为基准
        last_record = data[-1]
        baseline_pixel = last_record['像素距离']

        if baseline_pixel > 0:
            baseline_scale = 2.0 / baseline_pixel  # 2米/基准像素
            print(f"比例系数计算完成：1像素 = {baseline_scale:.4f} 米")

            # 为所有记录添加实物距离
            for record in data:
                real_distance = record['像素距离'] * baseline_scale
                record['实物距离（米）'] = round(real_distance, 2)
        else:
            print("警告：基准图片像素距离为0，无法计算实物距离")

        # 创建DataFrame
        df = pd.DataFrame(data)

        # 调整列顺序
        columns_order = ['图片名称',
                         '点1_X', '点1_Y',
                         '点2_X', '点2_Y',
                         '像素距离', '实物距离（米）']

        df = df[[col for col in columns_order if col in df.columns]]
        df.to_excel(output_excel, index=False)
        print(f"结果已保存到 {output_excel}")
    else:
        print("没有有效数据需要保存")


if __name__ == "__main__":
    # 使用示例
    image_folder = input("请输入图片文件夹路径：").strip()
    output_excel = "测量结果.xlsx"

    # 设置matplotlib使用TkAgg后端
    plt.switch_backend('TkAgg')

    select_points_and_calculate(image_folder, output_excel)
import os
import shutil


class ImageClassifier:
    def __init__(self, input_dir: str, result_dir: str, white_list: list) -> None:
        """
        __init__

        Args:
            input_dir (str): 输入文件夹
            result_dir (str): 输出文件夹（可以和输入是同一个）
            white_list (list): 后缀名过滤
        """

        self.input_dir = input_dir
        self.result_dir = result_dir
        self.num_processed_images = 0  # 用于报告
        self.sum_in_output = 0  # output文件夹具有的图片总数
        self.white_list = white_list  # 后缀名过滤
        self.prefix_recoder = self._get_prefix_recoder()  # 初始化，先获取当前result_dir中的所有有效序号

    def classify_images(self, use_copy: bool = True) -> None:
        """
        处理input_dir中的图片

        Args:
            use_copy (bool, optional): 使用copy或者move. 默认为True，即使用copy.
        """
        # 遍历输入文件夹中的所有文件夹
        for root, _, files in os.walk(self.input_dir):
            for file in files:
                # 跳过不在白名单中的文件类型
                _, extension = os.path.splitext(file)
                if extension not in self.white_list:
                    continue

                prefix = os.path.basename(root)  # 保存最接近的文件夹名作为prefix
                old_file_path = os.path.join(root, file)

                # 获取前缀的现有信息，包括已存在的序号和空位
                if prefix not in self.prefix_recoder.keys():
                    # 如果前缀不存在，初始化为无已存在序号, gaps 只含有元素 1
                    self.prefix_recoder[prefix] = {"existing_indices": set(), "gaps": {1}}

                existing_indices = self.prefix_recoder[prefix]["existing_indices"]
                gaps = self.prefix_recoder[prefix]["gaps"]

                # 处理新文件的命名逻辑
                if gaps:
                    # 如果存在空位，优先使用空位
                    new_index = min(gaps)  # 取空位中最小的
                    gaps.remove(new_index)  # 更新 gaps，移除已使用的空位
                else:
                    new_index = max(existing_indices, default=0) + 1  # 安全递增序号

                # 生成新文件名并复制文件
                new_file_name = f"{prefix}-{new_index}{extension}"
                new_file_path = os.path.join(self.result_dir, new_file_name)
                # 根据 use_copy 参数决定是使用 copy 还是 move
                if use_copy:
                    shutil.copy(old_file_path, new_file_path)
                else:
                    shutil.move(old_file_path, new_file_path)

                # 更新已存在的序号集合
                existing_indices.add(new_index)
                gaps = self._calculate_gaps(existing_indices)
                self.num_processed_images += 1  # 处理图片计数更新

        # 删除空文件夹
        self.remove_empty_folders(self.input_dir)

        # 处理完后创建索引文件
        self.creat_index_txt()

    def creat_index_txt(self) -> None:
        self.prefix_recoder = self._get_prefix_recoder()
        # 在outuput_dir生成目录
        with open(os.path.join(self.result_dir, "!index.txt"), "w") as f:
            prefix_list = list(self.prefix_recoder.keys())
            prefix_list.sort()
            for prefix in prefix_list:
                f.write(f"{prefix} : ")
                for index in self.prefix_recoder[prefix]["existing_indices"]:
                    f.write(f"{index},")
                f.write("\n")

    def _get_prefix_recoder(self, loglevel=False) -> dict:
        """
        获得已经存在的序号，即输出文件夹中图片的命名序号

        Args:
            loglevel (bool, optional): 是否输出不合法文件名，默认为False

        Returns:
            prefix_recoder (dict): 键为前缀名prefix，值为一个字典，
                                包含已存在序号的集合(existing_indices)
                                和中断点的集合(gaps)
        """
        prefix_recoder = {}
        self.sum_in_output = 0

        for root, _, files in os.walk(self.result_dir):
            for filename in files:
                if filename == "!index.txt":
                    continue  # 记录文件，应当跳过

                prefix, extension = os.path.splitext(filename)
                if extension not in self.white_list:
                    continue  # 跳过非白名单后缀

                try:
                    # 去除文件后缀名，然后根据分隔符"-"分割前缀与序号
                    prefix, index = prefix.split("-")
                    index = int(index)
                except ValueError:
                    if loglevel:
                        print(f"不合法文件：{filename}")
                    continue

                # 初始化 prefix_recoder 中对应 prefix 的字典
                if prefix not in prefix_recoder:
                    prefix_recoder[prefix] = {"existing_indices": set(), "gaps": set()}

                # 将序号加入已存在序号的集合中
                prefix_recoder[prefix]["existing_indices"].add(index)

                # 更新sum_in_output
                self.sum_in_output += 1

        # 计算每个 prefix 的中断点
        for prefix in prefix_recoder.keys():
            prefix_recoder[prefix]["gaps"] = self._calculate_gaps(prefix_recoder[prefix]["existing_indices"])

        return prefix_recoder

    def _calculate_gaps(self, prefix_recoder: set) -> set:
        """
        计算中断点，即未使用的序号

        Args:
            prefix_recoder (set): 已存在序号的集合

        Returns:
            gaps (set): 中断点的集合

        Note:
            其中最大的一个序号是可以安全递增的序号起始点（包括该序号）
        """
        if not prefix_recoder:
            return set()

        max_index = max(prefix_recoder)
        all_indices = set(range(1, max_index + 2))  # 包含到max_index + 1的所有序号
        gaps = all_indices - prefix_recoder
        return gaps

    def report_processed_images(self) -> None:
        print(f"共处理了 {self.num_processed_images} 张图片。")
        print(f"目前输出文件夹中共{self.sum_in_output}张图片。")

    def remove_empty_folders(self, directory: str) -> None:
        """删除空文件夹"""
        for root, dirs, _ in os.walk(directory, topdown=False):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                try:
                    os.rmdir(dir_path)  # 删除空文件夹
                except OSError:
                    # 如果文件夹不为空，捕捉异常
                    pass

    def _create_backup(self, src: str, dst: str) -> None:
        """创建输入文件夹的备份"""
        if os.path.exists(dst):
            shutil.rmtree(dst)  # 如果备份目录已存在，先删除
        shutil.copytree(src, dst)  # 复制整个输入目录到备份目录


def main() -> None:
    # 模式选取
    print("1: output -> !index.txt")
    print("2: input -> output + !index.txt (copy)")
    print("3: input -> output + !index.txt (move)")

    while True:
        value_input = input("")
        try:
            value = int(value_input)
            if value < 0:
                raise ValueError("非法输入")
            else:
                input_mode = value
                break
        except ValueError as e:
            print(f"输入错误：{e} 。请重新输入。")

    # 获取输入文件夹路径
    if input_mode >= 2:
        while True:
            input_dir = input("请输入输入文件夹路径：\n")
            if os.path.isdir(input_dir):
                break
            elif input_dir == ">":
                break
            else:
                print("输入文件夹不存在，请重新输入！")

    # 获取输出文件夹路径
    result_dir = input("请输入输出文件夹路径：\n")
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    # 创建 ImageClassifier 实例并执行分类
    white_list = [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"]
    if input_mode == 1:
        classifier = ImageClassifier(">", result_dir, white_list)
        classifier.creat_index_txt()
        classifier.report_processed_images()
    elif input_mode == 2:
        classifier = ImageClassifier(input_dir, result_dir, white_list)
        classifier.classify_images()
        classifier.report_processed_images()
    elif input_mode == 3:
        classifier = ImageClassifier(input_dir, result_dir, white_list)
        classifier.classify_images(False)
        classifier.report_processed_images()


# 在脚本直接运行时执行 main 函数
if __name__ == "__main__":
    main()

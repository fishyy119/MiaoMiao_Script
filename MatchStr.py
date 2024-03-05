import re
import os
'''
tudo:
match_matrix的处理有些不合理，尤其是一行内有多个非零项取第一项的部分
重命名大小写有问题
'''
class WordMatcher:
    '''
    list(字符串列表) --> word_list(单词集合的列表) --> match_matrix(映射矩阵)  --> match_map(映射列表)
    '''
    def __init__(self, list1, list2, pathlist1, pathlist2):
        self.list1 = list1  # 目标字符串列表
        self.list2 = list2  # 待对应字符串列表
        self.pathlist1 = pathlist1  # 路径列表
        self.pathlist2 = pathlist2
        self.word_list1 = []  # 单词集合的列表
        self.word_list2 = []  # 单词集合的列表
        self.match_matrix = []  # 映射矩阵,len(list1)xlen(list2)
        self.match_map = [-1] * len(list2)  # 剔除矩阵中的0项，将其精简为列表
        self.zero_positions = []  # 记录match_matrix处理中被消去的可能正确匹配
        pass

    @staticmethod
    def _extract_words(string):
        # 使用正则表达式提取所有单词字符组成的单词
        words = re.findall(r'\b\w+\b', string)
        return set(words)

    @staticmethod
    def _jaccard_similarity(set1, set2):
        # 计算相似度
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union
    
    def _cal_matrix(self):
        # 寻找每列的最大值，将其设为1，其他置0，并记录被置零项的坐标
        max_values = [max(col) for col in zip(*self.match_matrix)]  # 获取每列的最大值
        for j, col_max_value in enumerate(max_values):  # 遍历每列的最大值
            for i, value in enumerate(self.match_matrix):
                if value[j] == col_max_value and col_max_value != 0:  # 如果当前值等于该列的最大值(最大值为0说明完全不匹配，不应置1)
                    value[j] = 1  # 将其设为1
                else:
                    value[j] = 0  # 否则置为0
        
        # 检查每行是否只有一个非零项，生成match_map
        for i, row in enumerate(self.match_matrix):
            non_zero_index = None
            for j, value in enumerate(row):
                if value != 0:
                    if non_zero_index is None:
                        non_zero_index = j
                        self.match_map[j] = i
                    else:
                        self.match_matrix[i][j] = 0
                        self.zero_positions.append((i, j))

    def match_words(self):
        for string in self.list1:
            self.word_list1.append(self._extract_words(string))

        for string in self.list2:
            self.word_list2.append(self._extract_words(string))

        for idx, word1 in enumerate(self.word_list1):
            self.match_matrix.append([])
            for word2 in self.word_list2:
                self.match_matrix[idx].append(self._jaccard_similarity(word1, word2))
        
        self._cal_matrix()

class FileReader():
    def __init__(self, folder_path):
        self.folder_path = folder_path

    def read_filenames(self, file_extension, recursive=False):
        filenames = []
        pathlist = []
        if recursive: # 包括对子文件夹的扫描
            for root, dirs, files in os.walk(self.folder_path):
                for filename in files:
                    filename_lower = filename.lower()
                    for extension in file_extension:
                        if filename_lower.endswith(extension):
                            filenames.append(filename)
                            pathlist.append(os.path.join(root, filename))
        else: # 不包括子文件夹
            for filename in os.listdir(self.folder_path):
                filename_lower = filename.lower()
                for extension in file_extension:
                    if filename_lower.endswith(extension):
                        filenames.append(filename)
                        pathlist.append(os.path.join(self.folder_path, filename))
        
        if not filenames:
            input("目录下没有找到符合条件的文件。程序即将退出。")
            exit()  # 如果列表为空，退出程序
        return filenames, pathlist
    
    def rename_files(self, word_matcher):
        # 获取匹配文件列表与未匹配列表
        files_to_rename = []
        files_not_match = []
        for idx, matched_idx in enumerate(word_matcher.match_map):
            if matched_idx != -1:
                # 获取文件名
                old_filename = word_matcher.list2[idx]
                new_filename = word_matcher.list1[matched_idx]
                # 处理后缀
                old_filename_without_extension, old_extension = os.path.splitext(old_filename)
                new_filename_without_extension, _ = os.path.splitext(new_filename)
                # 构建文件的完整路径
                old_file_path = word_matcher.pathlist2[idx]
                new_file_path = word_matcher.pathlist1[matched_idx]  # 其中的后缀名需要处理
                new_file_path = os.path.join(os.path.dirname(new_file_path), new_filename_without_extension + old_extension)
                # 将文件信息添加到列表中
                files_to_rename.append((old_filename_without_extension, old_file_path, \
                                        new_filename_without_extension, new_file_path))
            else:
                old_filename = word_matcher.list2[idx]
                old_filename_without_extension, _ = os.path.splitext(old_filename)
                files_not_match.append(old_filename_without_extension)

        # 打印将要改名的文件列表
        print("\033[33m" + "未匹配到的文件列表：")
        for i, old_filename in enumerate(files_not_match):
            print(f"{i}. {old_filename}")
        print("\033[31m" + "可能被处理掉的正确对应：")
        for idx, (i, j) in enumerate(word_matcher.zero_positions):
            print("\033[31m" + f"{idx}.{word_matcher.list2[j]} \033[0m-x->\033[31m {word_matcher.list1[i]}" + "\033[0m")
        print("\033[0m将要改名的文件列表：")
        for i, (old_filename, _, new_filename, _) in enumerate(files_to_rename):
            print(f"{i}. {old_filename} --> {new_filename}")

        # 询问用户是否跳过某些文件
        skip_indices = []
        while True:
            response = input("请输入要跳过的文件序号（多个序号以逗号分隔），或直接按回车跳过：").strip()
            if response:
                try:
                    skip_indices = [int(idx) for idx in response.split(",")]
                    break
                except ValueError:
                    print("请输入有效的数字序号")
            else:
                break

        # 执行文件重命名操作
        renamed_count = 0
        skipped_count = 0
        error_count = 0
        for i, (old_filename, old_file_path, new_filename, new_file_path) in enumerate(files_to_rename):
            if i not in skip_indices:
                try:
                    os.rename(old_file_path, new_file_path)
                    print(f"重命名文件成功：{old_filename} --> {new_filename}")
                    renamed_count += 1
                except FileNotFoundError:
                    print(f"文件不存在：{old_filename}")
                    error_count += 1
                except Exception as e:
                    print(f"重命名文件{old_filename}时发生了错误：{str(e)}")
                    error_count += 1
            else:
                print(f"跳过文件：{old_filename}")
                skipped_count += 1

        # 打印结果报告
        print(f"成功重命名文件数：{renamed_count}，跳过文件数：{skipped_count}，失败文件数：{error_count}")

def get_validated_path(prompt="请输入文件夹路径：", default="."):
    while True:
        folder_path = input(prompt).strip()  # 获取用户输入并去除首尾空格
        if not folder_path:  # 如果用户没有输入任何内容，则使用默认值
            folder_path = default

        if os.path.exists(folder_path):  # 验证路径是否存在
            break
        else:
            print("路径不存在，请重新输入。")
        
    # 询问是否递归读取子文件夹
    recursive_input = input("是否递归读取子文件夹？(留空为否，任意字符为是): ").strip().lower()
    if recursive_input == "":
        recursive = False
    else:
        recursive = True

    return folder_path, recursive

if __name__ == "__main__":
    folder_path, recursive = get_validated_path()  # 文件路径，是否扫描子文件夹
    extension1 = [".mp3",".flac",".wav"]  # 作为改名目标文件名的类型
    extension2 = [".lrc"]  # 需要改名的类型
    file_reader = FileReader(folder_path)
    list1, pathlist1 = file_reader.read_filenames(extension1, recursive)
    list2, pathlist2 = file_reader.read_filenames(extension2, recursive)

    word_matcher = WordMatcher(list1, list2, pathlist1, pathlist2)
    word_matcher.match_words()

    file_reader.rename_files(word_matcher)
    # print(word_matcher.match_map)
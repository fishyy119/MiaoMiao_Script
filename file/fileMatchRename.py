import re
from pathlib import Path
from typing import Dict, List, Tuple


class WordMatcher:
    """
    List(字符串列表) --> word_list(单词集合的列表) --> match_matrix(映射矩阵)  --> match_map(映射列表)
    """

    def __init__(
        self,
        list1: List[str],
        list2: List[str],
        pathlist1: List[Path],
        pathlist2: List[Path],
        black_list1: List[str],
        black_list2: List[str],
        synonyms: Dict[str, str],
        ENHANCE_DIGIT_WEIGHT: bool = True,
        DIGIT_REPEAT: int = 3,
    ) -> None:
        """
        Args:
            list1 (List[str]): 目标字符串列表。
            list2 (List[str]): 待匹配的字符串列表。
            pathlist1 (List[Path]): 与 list1 对应的路径列表。
            pathlist2 (List[Path]): 与 list2 对应的路径列表。
            black_list1 (List[str]): 词组黑名单，含有其中的字符串的文件将被忽略（大小写不敏感），对应list1
            black_list2 (List[str]): 同上，对应list2
            synonyms (Dict[str, str]): 用于替换的同义词字典。
            ENHANCE_DIGIT_WEIGHT (bool, optional): 是否增强数字的权重。默认为 True。
            DIGIT_REPEAT (int, optional): 增强权重时数字重复的次数。默认为 3。
        """
        self.list1 = list1  # 目标字符串列表
        self.list2 = list2  # 待对应字符串列表
        self.pathlist1 = pathlist1  # 路径列表，与上方列表一一对应
        self.pathlist2 = pathlist2
        self.synonyms = synonyms  # 同义词替换的储存

        # 含有其中的字符串的文件将被忽略
        self.black_list1 = [word.lower() for word in black_list1]
        self.black_list2 = [word.lower() for word in black_list2]

        # 单词集合的列表（因为希望有重复单词，所以用了列表，其中重复单词主要用于提高纯数字序号的权重）
        self.word_list1: List[List[str]] = []
        self.word_list2: List[List[str]] = []
        self.ENHANCE_DIGIT_WEIGHT = ENHANCE_DIGIT_WEIGHT
        self.DIGIT_REPEAT = DIGIT_REPEAT

        self.match_matrix: List[List[float]] = []  # 映射矩阵,len(list1)xlen(list2)
        self.match_map = [-1] * len(list2)  # 直接用于重命名的映射列表
        self.zero_positions = []  # 记录match_matrix处理中被消去的可能正确匹配(未用到)
        pass

    def _extract_words(self, string: str, list_index: int) -> List[str]:
        # 使用正则表达式提取所有单词字符组成的单词
        words: List[str] = re.findall(r"\b\w+\b", string)
        enhance_digit: List[str] = []
        # 小写化与同义词替换（仅用于相似度计算，不用于改名）
        for idx, word in enumerate(words):
            word = word.lower()
            if list_index == 1 and word in self.black_list1:
                return []  # 如果有黑名单词组，直接返回空集
            elif list_index == 2 and word in self.black_list2:
                return []  # 如果有黑名单词组，直接返回空集

            if word in self.synonyms.keys():
                word = self.synonyms.get(word, word)

            # 用于加强数字词组的权重，通过重复其若干次，同时数字的前导零会被清除
            if self.ENHANCE_DIGIT_WEIGHT:
                has_digit = bool(re.search(r"\d", word))
                has_non_english = bool(re.search(r"[^A-Za-z0-9]", word))

                if has_digit and has_non_english:
                    digits: List[str] = re.findall(r"\d+", word)
                    for digit in digits:
                        enhance_digit.extend([str(int(digit))] * (self.DIGIT_REPEAT))

                if word.isdigit():
                    word = str(int(word))  # 去掉前导零
                    enhance_digit.extend([word] * (self.DIGIT_REPEAT - 1))

            words[idx] = word

        # 循环里面积累的重复项在这里一并添加进来
        words.extend(enhance_digit)
        return words

    @staticmethod
    def _jaccard_similarity(list1: List[str], list2: List[str]) -> float:
        # 计算相似度，考虑重复单词
        set1 = list1
        set2 = list2
        intersection = sum((min(set1.count(word), set2.count(word)) for word in set(set1).intersection(set(set2))))
        union = len(set1) + len(set2) - intersection
        return intersection / union if union != 0 else 0

    def _init_similarity_matrix(self) -> None:
        # 初始化相似度矩阵
        for word1 in self.word_list1:
            row: List[float] = []
            for word2 in self.word_list2:
                similarity = self._jaccard_similarity(word1, word2)
                row.append(similarity)
            self.match_matrix.append(row)

    def _find_stable_match(self) -> None:
        # 稳定匹配的G-S算法（略过偏好0项）
        # 双方的偏好列表都共享自match_matrix
        # 查询方式：match_matrix[S_index][L_index]
        # 歌词L为主动方，歌曲S为被动方

        # 转置，此变量会被更改用于记录其他信息，self.match_matrix保持不变
        match_matrix_T: List[List[float]] = []
        for i in range(len(self.match_matrix[0])):
            temp: List[float] = []
            for j in range(len(self.match_matrix)):
                temp.append(self.match_matrix[j][i])
            match_matrix_T.append(temp)

        L_prefs = {L: list(range(len(self.list1))) for L in range(len(self.list2))}  # 用于记录L的待匹配项
        free_L = list(range(len(self.list2)))
        match_dict: Dict[int, int] = {}  # 顺序S: L

        while free_L:
            L = free_L.pop(0)
            if len(L_prefs[L]) == 0:  # 已经配过过所有歌曲的L:不再进行匹配，相当于被移出free_L
                continue
            if max(match_matrix_T[L]) == 0:  # 已经全为0，无需匹配（强行匹配会出错），相当于被移出free_L
                continue
            else:
                S = match_matrix_T[L].index(max(match_matrix_T[L]))  # 取出最优的歌曲
                match_matrix_T[L][S] = 0  # 避免下次取到同一个最优歌曲
                L_prefs[L].remove(S)  # 真正意义上的取出

            if self.match_matrix[S][L] != 0:  # 忽略相似度为0项
                if S not in match_dict:  # S未匹配，则进行配对
                    match_dict[S] = L
                else:  # S已匹配，比较现有匹配与新匹配的相似度
                    L2 = match_dict[S]
                    if self.match_matrix[S][L] > self.match_matrix[S][L2]:
                        free_L.append(L2)
                        match_dict[S] = L
                    else:
                        free_L.append(L)
            else:
                free_L.append(L)  # 加回去

        for _S, _L in match_dict.items():
            self.match_map[_L] = _S

    def match_words(self) -> None:
        for string in self.list1:
            self.word_list1.append(self._extract_words(string, list_index=1))

        for string in self.list2:
            self.word_list2.append(self._extract_words(string, list_index=2))

        self._init_similarity_matrix()
        self._find_stable_match()


class FileReader:
    def __init__(self, folder_path: Path, SUFFIX_PART_LENGTH_THRESHOLD: int = 10, SUFFIX_PART_MAX_NUM: int = 2) -> None:
        """
        Args:
            folder_path (Path): 工作的文件夹路径
            SUFFIX_PART_LENGTH_THRESHOLD (int, optional): 用于识别多个字段串联的后缀名，如".tc.ass"，根据长度筛选
            SUFFIX_PART_MAX_NUM (int, optional): 用于识别多个字段串联的后缀名，如".tc.ass"，通关限制段数实现
            TODO: 上面两个参数...
        """
        self.folder_path = folder_path
        self.SUFFIX_PART_LENGTH_THRESHOLD = SUFFIX_PART_LENGTH_THRESHOLD
        self.SUFFIX_PART_MAX_NUM = SUFFIX_PART_MAX_NUM

    def read_filenames(self, file_extension: List[str], recursive: bool = False) -> Tuple[List[str], List[Path]]:
        filenames: List[str] = []
        pathlist: List[Path] = []
        if recursive:  # 包括对子文件夹的扫描
            for path in self.folder_path.rglob("*"):
                if path.is_file() and any(path.name.lower().endswith(ext) for ext in file_extension):
                    filenames.append(path.name)
                    pathlist.append(path)
        else:  # 不包括子文件夹
            for path in self.folder_path.glob("*"):
                if path.is_file() and any(path.name.lower().endswith(ext) for ext in file_extension):
                    filenames.append(path.name)
                    pathlist.append(path)

        if not filenames:
            input("目录下没有找到符合条件的文件。程序即将退出。")
            exit()  # 如果列表为空，退出程序
        return filenames, pathlist

    def rename_files(self, word_matcher: WordMatcher) -> None:
        # 获取匹配文件列表与未匹配列表
        files_to_rename: List[Tuple[Path, Path]] = []
        files_not_match: List[str] = []
        for idx, matched_idx in enumerate(word_matcher.match_map):
            if matched_idx != -1:
                # 获取文件名
                old_file_path = word_matcher.pathlist2[idx]
                new_file_path = word_matcher.pathlist1[matched_idx]  # 其中的后缀名需要处理
                old_filename = old_file_path.name

                # 保留一些额外的标注性后缀，如".tc.ass"，根据长度筛选
                old_filename_parts = old_filename.rsplit(".")
                old_extension = ""
                part_num = 0  # 用于计数后缀名的段数
                for word in reversed(old_filename_parts):
                    if len(word) > self.SUFFIX_PART_LENGTH_THRESHOLD:
                        break
                    old_extension = "." + word + old_extension
                    part_num += 1
                    if part_num >= self.SUFFIX_PART_MAX_NUM:
                        break

                new_filename_without_extension = new_file_path.stem
                # 构建文件的完整路径
                new_file_path = new_file_path.parent / (new_filename_without_extension + old_extension)
                # 将文件信息添加到列表中
                files_to_rename.append((old_file_path, new_file_path))
            else:
                old_filename = word_matcher.pathlist2[idx].name
                files_not_match.append(old_filename)

        # 打印将要改名的文件列表
        print("\033[33m" + "未匹配到的文件列表：")
        for i, old_filename in enumerate(files_not_match):
            print(f"{i}. {old_filename}")
        print("\033[32m将要改名的文件列表：\033[0m")
        for i, (old_file, new_file) in enumerate(files_to_rename):
            print(f"{i}. {old_file.name} --> \033[32m{new_file.name}\033[0m")

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
        for i, (old_file, new_file) in enumerate(files_to_rename):
            if i not in skip_indices:
                try:
                    old_file.rename(new_file)
                    print(f"重命名文件成功：{old_file.name} --> {new_file.name}")
                    renamed_count += 1
                except FileNotFoundError:
                    print(f"\033[31m文件不存在：{old_file.name}\033[0m")
                    error_count += 1
                except Exception as e:
                    print(f"\033[31m重命名文件{old_file.name}时发生了错误：{str(e)}\033[0m")
                    error_count += 1
            else:
                print(f"跳过文件：{old_file.name}")
                skipped_count += 1

        # 打印结果报告
        print(f"成功重命名文件数：{renamed_count}，跳过文件数：{skipped_count}，失败文件数：{error_count}")


def get_validated_path(prompt: str = "请输入文件夹路径：", default: str = ".") -> Tuple[Path, bool]:
    while True:
        folder_path = input(prompt).strip()  # 获取用户输入并去除首尾空格
        if not folder_path:  # 如果用户没有输入任何内容，则使用默认值
            folder_path = default

        path = Path(folder_path)
        if path.exists():  # 验证路径是否存在
            break
        else:
            print("路径不存在，请重新输入。")

    # 询问是否递归读取子文件夹
    recursive_input = input("是否递归读取子文件夹？(留空为否，任意字符为是): ").strip().lower()
    if recursive_input == "":
        recursive = False
    else:
        recursive = True

    return path, recursive


if __name__ == "__main__":
    #############################################################################
    extension1 = [".mp3", ".flac", ".wav", ".mkv"]  # 作为改名目标文件名的类型
    extension2 = [".lrc", ".ass"]  # 需要改名的类型
    synonyms = {"version": "ver", "instrumental": "inst"}  # 同义词的替换
    black_list1 = ["NCOP", "NCED", "SP"]  # 忽略有这些词组的文件（大小写不敏感），对应前面extension1的文件
    black_list2 = ["TUcaptions", "SP"]  # 对应前面extension2的文件
    ENHANCE_DIGIT_WEIGHT = True  # 数字词组的增强选项，开启后会将数字词组重复若干次来间接增加其权重，同时前导零会被去除
    DIGIT_REPEAT = 3  # 数字词组的重复次数（在前面`ENHANCE_DIGIT_WEIGHT`开启时有效）
    SUFFIX_PART_LENGTH_THRESHOLD = 10  # 用于识别多个字段串联的后缀名，如".tc.ass"，此处为每一段的长度阈值
    SUFFIX_PART_MAX_NUM = 2  # 同上，这个设置最大段数
    #############################################################################
    folder_path, recursive = get_validated_path()  # 文件路径，是否扫描子文件夹
    file_reader = FileReader(folder_path, SUFFIX_PART_LENGTH_THRESHOLD=SUFFIX_PART_LENGTH_THRESHOLD)
    list1, pathlist1 = file_reader.read_filenames(extension1, recursive)
    list2, pathlist2 = file_reader.read_filenames(extension2, recursive)

    word_matcher = WordMatcher(
        list1,
        list2,
        pathlist1,
        pathlist2,
        black_list1,
        black_list2,
        synonyms,
        ENHANCE_DIGIT_WEIGHT=ENHANCE_DIGIT_WEIGHT,
        DIGIT_REPEAT=DIGIT_REPEAT,
    )
    word_matcher.match_words()

    file_reader.rename_files(word_matcher)

    # print(word_matcher.match_matrix)
    # print(word_matcher.match_map)

import shutil
from pathlib import Path


def fix_nested_dirs(root_dir: Path) -> None:
    """
    扫描 root_dir 下的所有子目录，修复 a/a 这种重复目录结构。

    条件：
    1. 父目录名和子目录名相同
    2. 父目录下没有其他内容（只包含这个子目录）
    """
    # 自底向上遍历
    for current_dir in sorted(root_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not current_dir.is_dir():
            continue

        parent = current_dir.parent
        # if parent == root_dir:
        #     # 根目录下的同名子目录不处理
        #     continue

        if current_dir.name == parent.name:
            siblings = list(parent.iterdir())
            if len(siblings) == 1 and siblings[0] == current_dir:
                print(f"[+] Fixing: {parent} (removing nested {current_dir})")

                for item in current_dir.iterdir():
                    dst = parent / item.name
                    if dst.exists():
                        print(f"    [!] Skipping {item}, already exists at {dst}")
                        continue
                    shutil.move(str(item), str(dst))

                current_dir.rmdir()


def main() -> None:
    root: Path = Path(input("目标文件夹："))
    fix_nested_dirs(root)


if __name__ == "__main__":
    main()

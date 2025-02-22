from pathlib import Path


def main() -> None:
    folder: str = input("目标文件夹：")
    target_suffix: str = ".nfo"
    count: int = 0

    for path in Path(folder).rglob("*" + target_suffix):
        path.unlink(missing_ok=True)
        count += 1

    print(f"共删除{count}个文件")


if __name__ == "__main__":
    main()

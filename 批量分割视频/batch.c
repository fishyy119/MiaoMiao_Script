#include <stdio.h>
#include <stdlib.h>

int main() {
    FILE *file;
    int ss, to, check;
    char command[256];
    int start_value, count;

    printf("功能：根据target.txt中的数对(每行2个)分割0.mp4，抛弃音频\n");
    // 获取用户输入的起始值
    printf("请输入输出文件名的起始值：");
    scanf("%d", &start_value);

    // 设置计数器为起始值
    count = start_value;

    // 打开 target.txt 文件
    file = fopen("target.txt", "r");
    if (file == NULL) {
        perror("无法打开文件target.txt");
        return 1;
    }

    // 逐行读取文件内容
    while (check = fscanf(file, "%d %d", &ss, &to)) {
        // check相关的退出逻辑
        if (check == EOF) {
            break;
        }
        else if (check != 2) {
            printf("读取出错，请检查target.txt是否存在多余字符\n");
            break;
        }

        // 生成输出文件名
        char output_file[20];
        sprintf(output_file, "%d.mp4", count);

        // 构建 ffmpeg 命令
        sprintf(command, "ffmpeg -loglevel error -ss %d -to %d -i 0.mp4 -an -c:v copy %s", ss, to, output_file);

        // 执行命令
        system(command);

        printf("执行成功：%s\n", command);

        // 增加计数器
        count++;
    }

    // 关闭文件
    fclose(file);
    system("PAUSE");

    return 0;
}

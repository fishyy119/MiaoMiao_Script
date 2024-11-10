#include <stdio.h>
#include <stdlib.h>

int main() {
    FILE *file;
    int ss, to;
    char command[256];
    int start_value, count, target;

    // 设置计数器为起始值
    count = start_value;

    // 打开 target.txt 文件
    file = fopen("target.txt", "r");
    if (file == NULL) {
        perror("无法打开文件");
        return 1;
    }

    // 逐行读取文件内容
    while (fscanf(file, "%d", &target) != EOF) {
        // 生成输出文件名
        char output_file[20];
        sprintf(output_file, "%d_.mp4", target);

        // 构建 ffmpeg 命令
        sprintf(command, "ffmpeg -loglevel error -ss 1 -i %d.mp4 -an -c:v copy %s", target, output_file);

        // 执行命令
        system(command);

        // 删除
        sprintf(command, "del %d.mp4", target);
        system(command);

        // 重命名
        sprintf(command, "ren %d_.mp4 %d.mp4", target, target);
        system(command);
        printf("处理完毕：%d.mp4\n", target);
    }

    // 关闭文件
    fclose(file);
    system("PAUSE");

    return 0;
}

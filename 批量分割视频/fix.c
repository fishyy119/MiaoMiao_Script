#include <stdio.h>
#include <stdlib.h>

int main() {
    FILE *file;
    int ss, to;
    char command[256];
    int start_value, count, target;

    // ���ü�����Ϊ��ʼֵ
    count = start_value;

    // �� target.txt �ļ�
    file = fopen("target.txt", "r");
    if (file == NULL) {
        perror("�޷����ļ�");
        return 1;
    }

    // ���ж�ȡ�ļ�����
    while (fscanf(file, "%d", &target) != EOF) {
        // ��������ļ���
        char output_file[20];
        sprintf(output_file, "%d_.mp4", target);

        // ���� ffmpeg ����
        sprintf(command, "ffmpeg -loglevel error -ss 1 -i %d.mp4 -an -c:v copy %s", target, output_file);

        // ִ������
        system(command);

        // ɾ��
        sprintf(command, "del %d.mp4", target);
        system(command);

        // ������
        sprintf(command, "ren %d_.mp4 %d.mp4", target, target);
        system(command);
        printf("������ϣ�%d.mp4\n", target);
    }

    // �ر��ļ�
    fclose(file);
    system("PAUSE");

    return 0;
}

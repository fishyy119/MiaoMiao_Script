#include <stdio.h>
#include <stdlib.h>

int main() {
    FILE *file;
    int ss, to, check;
    char command[256];
    int start_value, count;

    printf("���ܣ�����target.txt�е�����(ÿ��2��)�ָ�0.mp4��������Ƶ\n");
    // ��ȡ�û��������ʼֵ
    printf("����������ļ�������ʼֵ��");
    scanf("%d", &start_value);

    // ���ü�����Ϊ��ʼֵ
    count = start_value;

    // �� target.txt �ļ�
    file = fopen("target.txt", "r");
    if (file == NULL) {
        perror("�޷����ļ�target.txt");
        return 1;
    }

    // ���ж�ȡ�ļ�����
    while (check = fscanf(file, "%d %d", &ss, &to)) {
        // check��ص��˳��߼�
        if (check == EOF) {
            break;
        }
        else if (check != 2) {
            printf("��ȡ��������target.txt�Ƿ���ڶ����ַ�\n");
            break;
        }

        // ��������ļ���
        char output_file[20];
        sprintf(output_file, "%d.mp4", count);

        // ���� ffmpeg ����
        sprintf(command, "ffmpeg -loglevel error -ss %d -to %d -i 0.mp4 -an -c:v copy %s", ss, to, output_file);

        // ִ������
        system(command);

        printf("ִ�гɹ���%s\n", command);

        // ���Ӽ�����
        count++;
    }

    // �ر��ļ�
    fclose(file);
    system("PAUSE");

    return 0;
}

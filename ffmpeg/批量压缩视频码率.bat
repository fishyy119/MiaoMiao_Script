@echo off
setlocal enabledelayedexpansion

REM �˴�ָ��Ŀ�����ʣ����磺1000k��
set target_bitrate=1500k

REM ����ļ��еĴ���
mkdir result

REM ������ǰĿ¼�����е�mp4�ļ�
for %%f in (*.mp4) do (
    REM ��ȡ�ļ�������������չ����
    set filename=%%~nf
    

    REM ѹ����Ƶ�ļ�
    echo ��ʼѹ����!filename!
    ffmpeg -i "%%f" -b:v %target_bitrate% -loglevel error "result\!filename!.mp4"
    echo ��ѹ����!filename!

)

echo ѹ����ɣ�
pause

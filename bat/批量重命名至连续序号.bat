@echo off
setlocal enabledelayedexpansion

REM ��ʼ��ţ��˹�ָ��
set /A index=520

del map.txt

REM ������ǰĿ¼�����е�mp4�ļ�
for %%f in (*.mp4) do (
    REM ��ȡ�ļ�������������չ����
    set filename=%%~nf

    ren "!filename!.mp4" !index!.mp4
    echo !index! = !filename! >> map.txt
    echo !index! = !filename!
    set /A index=index+1

)

echo ���
pause
exit /b


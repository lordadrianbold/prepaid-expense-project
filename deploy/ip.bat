@echo off
REM Prints the demo's public address. Run after status.bat shows runningCount=1.
setlocal
set CL=ts-forecast-cluster
set SV=prepaid-expense-service
set RG=us-east-1
set TASK=
set ENI=
set IP=

for /f "usebackq delims=" %%i in (`aws ecs list-tasks --cluster %CL% --service-name %SV% --region %RG% --query "taskArns[0]" --output text`) do set TASK=%%i
if "%TASK%"=="" goto :notask
if "%TASK%"=="None" goto :notask

for /f "usebackq delims=" %%i in (`aws ecs describe-tasks --cluster %CL% --tasks %TASK% --region %RG% --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text`) do set ENI=%%i
if "%ENI%"=="" goto :noeni

for /f "usebackq delims=" %%i in (`aws ec2 describe-network-interfaces --network-interface-ids %ENI% --region %RG% --query "NetworkInterfaces[0].Association.PublicIp" --output text`) do set IP=%%i
if "%IP%"=="" goto :noip
if "%IP%"=="None" goto :noip

echo.
echo Health check:  http://%IP%:8000/health
echo The demo:      http://%IP%:8000
exit /b 0

:notask
echo No running task found. Run deploy\status.bat. If runningCount is 0, run deploy\start.bat and wait a minute or two.
exit /b 1
:noeni
echo Task found but its network interface is not ready yet. Wait a minute and run this again.
exit /b 1
:noip
echo No public IP yet. Wait a minute and run this again.
exit /b 1





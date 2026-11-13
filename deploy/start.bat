@echo off
REM Starts the Project 6 demo (scales to 1 task). Takes a minute or two. Then run deploy\ip.bat for the address.
aws ecs update-service --cluster ts-forecast-cluster --service prepaid-expense-service --desired-count 1 --region us-east-1 --no-cli-pager
echo.
echo Start requested. Check with deploy\status.bat, then run deploy\ip.bat for the address.




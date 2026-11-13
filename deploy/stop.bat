@echo off
REM Stops the Project 6 demo (scales to 0 tasks) so it stops billing.
aws ecs update-service --cluster ts-forecast-cluster --service prepaid-expense-service --desired-count 0 --region us-east-1 --no-cli-pager
echo.
echo Stop requested. Check with deploy\status.bat (running should reach 0).




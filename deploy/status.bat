@echo off
REM Shows whether the Project 6 demo is running (and billing). Run from the project root: deploy\status.bat
aws ecs describe-services --cluster ts-forecast-cluster --services prepaid-expense-service --region us-east-1 --query "services[0].{status:status,desiredCount:desiredCount,runningCount:runningCount,pendingCount:pendingCount}" --no-cli-pager
echo.
echo desiredCount=0 and runningCount=0 means it is fully stopped and NOT billing.
echo desiredCount=1 and runningCount=1 means it is live and billing.




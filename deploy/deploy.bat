@echo off
REM Project 6: deploy to ECS Fargate from plain cmd (same six steps as Projects 1-5).
REM Run from the project root:   deploy\deploy.bat
REM Needs: Docker Desktop running and the AWS CLI configured.
setlocal

set AWS_ACCOUNT_ID=816069143878
set AWS_REGION=us-east-1
set ECR_REPO=prepaid-expense-service
set CLUSTER_NAME=ts-forecast-cluster
set SERVICE_NAME=prepaid-expense-service
set REGISTRY=%AWS_ACCOUNT_ID%.dkr.ecr.%AWS_REGION%.amazonaws.com

echo Step 1: Create the ECR repository if it does not exist
aws ecr describe-repositories --repository-names %ECR_REPO% --region %AWS_REGION% >nul 2>&1
if errorlevel 1 (
    aws ecr create-repository --repository-name %ECR_REPO% --region %AWS_REGION%
    if errorlevel 1 goto :fail
)

echo Step 2: Log Docker in to ECR
aws ecr get-login-password --region %AWS_REGION% | docker login --username AWS --password-stdin %REGISTRY%
if errorlevel 1 goto :fail

echo Step 3: Build the Docker image
docker build -t %ECR_REPO%:latest .
if errorlevel 1 goto :fail

echo Step 4: Tag and push to ECR
docker tag %ECR_REPO%:latest %REGISTRY%/%ECR_REPO%:latest
if errorlevel 1 goto :fail
docker push %REGISTRY%/%ECR_REPO%:latest
if errorlevel 1 goto :fail

echo Step 5: Register the task definition
aws ecs register-task-definition --cli-input-json file://deploy/task-definition.json --region %AWS_REGION%
if errorlevel 1 goto :fail

echo Step 6: Update the service, or create it the first time
aws ecs update-service --cluster %CLUSTER_NAME% --service %SERVICE_NAME% --task-definition %SERVICE_NAME% --desired-count 1 --force-new-deployment --region %AWS_REGION% >nul 2>&1
if not errorlevel 1 (
    echo Service updated.
    goto :done
)
aws ecs create-service --cluster %CLUSTER_NAME% --service-name %SERVICE_NAME% --task-definition %SERVICE_NAME% --desired-count 1 --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[subnet-0999558e22451c8c6],securityGroups=[sg-02ca18d50c6940d81],assignPublicIp=ENABLED}" --region %AWS_REGION%
if errorlevel 1 goto :fail

:done
echo.
echo Done. Find the task public IP in the ECS console (cluster %CLUSTER_NAME% - service %SERVICE_NAME% - Tasks - Networking), then open http://IP:8000
echo Status:  aws ecs describe-services --cluster %CLUSTER_NAME% --services %SERVICE_NAME% --region %AWS_REGION%
exit /b 0

:fail
echo.
echo STOPPED: the step above failed. Copy the error message and send it to me.
exit /b 1





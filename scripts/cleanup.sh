#!/usr/bin/env bash
# Usage:
# ./scripts/cleanup.sh <bucket> <table> <function> <queue> <policy> <role> [alarm ...]
# Example:
# ./scripts/cleanup.sh lab4-maksymchuk-2026 lab4-items lab4-processor lab4-dlq \
# lab4-processor-policy lab4-processor-role-8z6k2mtd \
# lab4-processor-errors lab4-dlq-messages
set -u
if [ "$#" -lt 6 ]; then
  echo "Потрібно мінімум 6 аргументів, див. коментар на початку файлу"
  exit 1
fi
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-north-1}"
BUCKET=$1; TABLE=$2; FUNC=$3; QUEUE=$4; POLICY=$5; ROLE=$6
shift 6

echo "Буде видалено: бакет $BUCKET, таблицю $TABLE, функцію $FUNC, чергу $QUEUE,"
echo "політику $POLICY, роль $ROLE, алярми: $*"
read -r -p "Продовжити? (yes/no) " ans
[ "$ans" = "yes" ] || { echo "Скасовано"; exit 0; }

if [ "$#" -gt 0 ]; then
  echo "Алярми"; aws cloudwatch delete-alarms --alarm-names "$@"
fi
echo "Lambda";   aws lambda delete-function --function-name "$FUNC"
echo "S3";       aws s3 rb "s3://$BUCKET" --force
echo "DynamoDB"; aws dynamodb delete-table --table-name "$TABLE"
echo "SQS"
URL=$(aws sqs get-queue-url --queue-name "$QUEUE" --query QueueUrl --output text) \
  && aws sqs delete-queue --queue-url "$URL"
echo "IAM"
aws iam delete-role-policy --role-name "$ROLE" --policy-name "$POLICY"
for ARN in $(aws iam list-attached-role-policies --role-name "$ROLE" \
             --query 'AttachedPolicies[].PolicyArn' --output text); do
  aws iam detach-role-policy --role-name "$ROLE" --policy-arn "$ARN"
  aws iam delete-policy --policy-arn "$ARN"
done
aws iam delete-role --role-name "$ROLE"
echo "Логи"; aws logs delete-log-group --log-group-name "/aws/lambda/$FUNC"
echo "Готово. Завтра перевірте Cost Explorer."
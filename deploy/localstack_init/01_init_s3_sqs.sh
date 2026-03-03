#!/bin/bash

echo "🚀 Initializing LocalStack S3 and SQS..."

# Create S3 bucket (must match BUCKET_NAME in .env)
awslocal s3 mb s3://performance-studio-bucket
echo "✅ S3 bucket 'performance-studio-bucket' created"

# Create SQS queue
awslocal sqs create-queue --queue-name performance-studio-queue
echo "✅ SQS queue 'performance-studio-queue' created"

# Get queue URL
QUEUE_URL=$(awslocal sqs get-queue-url --queue-name performance-studio-queue --output text)
echo "✅ Queue URL: $QUEUE_URL"

echo "🎉 LocalStack initialization complete!"



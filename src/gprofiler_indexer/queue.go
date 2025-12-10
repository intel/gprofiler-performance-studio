//
// Copyright (C) 2023 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

package main

import (
	"context"
	"encoding/json"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/sqs"
	"io/ioutil"
	"path/filepath"
	"sync"
)

type SQSMessage struct {
	Filename      string `json:"filename"`
	Service       string `json:"service"`
	ServiceId     int    `json:"service_id"`
	MessageHandle string
	QueueURL      string
}

func getQueueURL(sess *session.Session, queue string) (*sqs.GetQueueUrlOutput, error) {
	svc := sqs.New(sess)

	urlResult, err := svc.GetQueueUrl(&sqs.GetQueueUrlInput{
		QueueName: &queue,
	})
	if err != nil {
		return nil, err
	}

	return urlResult, nil
}

func ListenSqs(ctx context.Context, args *CLIArgs, ch chan<- SQSMessage, wg *sync.WaitGroup) {
	defer wg.Done()
	sessionOptions := session.Options{
		SharedConfigState: session.SharedConfigEnable,
	}
	if args.AWSEndpoint != "" {
		sessionOptions.Config = aws.Config{
			Region:   aws.String(args.AWSRegion),
			Endpoint: aws.String(args.AWSEndpoint),
		}
	}
	sess := session.Must(session.NewSessionWithOptions(sessionOptions))
	svc := sqs.New(sess)
	urlResult, err := getQueueURL(sess, args.SQSQueue)

	if err != nil {
		logger.Errorf("Got an error getting the queue URL: %v", err)
		
		// SLI Metric: SQS queue URL resolution failure (infrastructure error - counts against SLO)
		return
	}

	for {
		select {
		case <-ctx.Done():
			logger.Debug("ListenSQS finished")
			return
		default:
			output, recvErr := svc.ReceiveMessage(&sqs.ReceiveMessageInput{
				QueueUrl:            urlResult.QueueUrl,
				MaxNumberOfMessages: aws.Int64(1),
				WaitTimeSeconds:     aws.Int64(10),
			})
			if recvErr != nil {
				logger.Error(recvErr)
				
				// SLI Metric: SQS message receive failure (infrastructure error - counts against SLO)
				continue
			}

			for _, message := range output.Messages {
				var sqsMessage SQSMessage
				parseErr := json.Unmarshal([]byte(*message.Body), &sqsMessage)
				if parseErr != nil {
					logger.Errorf("Error while parsing SQS message body: %v", parseErr)
					
					// SLI Metric: SQS message parse failure (client error - malformed JSON)
					
					// Delete malformed messages to prevent infinite retry loop
					// This is a permanent client error that won't be fixed by retrying
					svc := sqs.New(sess)
					_, deleteErr := svc.DeleteMessage(&sqs.DeleteMessageInput{
						QueueUrl:      urlResult.QueueUrl,
						ReceiptHandle: message.ReceiptHandle,
					})
					if deleteErr != nil {
						logger.Errorf("Failed to delete malformed message: %v", deleteErr)

						// SLI Metric: SQS message deletion failure (infrastructure error - counts against SLO)
					} else {
						logger.Warnf("Deleted malformed SQS message to prevent reprocessing")
					}
					continue
				}
				sqsMessage.QueueURL = *urlResult.QueueUrl
				sqsMessage.MessageHandle = *message.ReceiptHandle
				ch <- sqsMessage
			}
		}
	}
}

func deleteMessage(sess *session.Session, queueURL string, messageHandle string) error {
	svc := sqs.New(sess)

	_, err := svc.DeleteMessage(&sqs.DeleteMessageInput{
		QueueUrl:      &queueURL,
		ReceiptHandle: &messageHandle,
	})
	if err != nil {
		return err
	}

	return nil
}

func ProcessFolder(ctx context.Context, ch chan<- SQSMessage, inputFolder string, wg *sync.WaitGroup) {
	defer wg.Done()
	files, err := ioutil.ReadDir(inputFolder)
	if err != nil {
		logger.Errorf("unable to open directory %s, err: %v", inputFolder, err)
		return
	}
	for _, file := range files {
		message := SQSMessage{
			Filename:      filepath.Join(inputFolder, file.Name()),
			ServiceId:     1,
			QueueURL:      "",
			MessageHandle: "",
		}
		ch <- message
	}
}

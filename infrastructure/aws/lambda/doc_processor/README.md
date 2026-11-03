# doc_processor Lambda (M8 Task 8.3)

`handler.py` is the whole function: standard library plus boto3, which the Lambda runtime already includes, so there are no dependencies to bundle. Deploy it with `bash scripts/aws/lambda-deploy.sh`, test it with `python3 -m unittest discover -s infrastructure/aws/lambda/doc_processor/tests -v`, and see the design in [docs/architecture/aws-document-lambda.md](../../../../docs/architecture/aws-document-lambda.md).

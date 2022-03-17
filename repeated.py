import re
import datetime
import time

client = boto3.client('logs')

log_group_name = 'auctionScraper'
log_stream_name = datetime.datetime.now().strftime('%Y-%m-%d %H_%M_%S')
seq_token = None


def init_stream():
    # create steam on cloudWatch by time str
    global log_stream_name
    global log_group_name

    for i in range(30):
        print(f"Creating Stream: {log_stream_name} on CloudWatch")

        time.sleep(2)

        try:
            response = client.create_log_stream(
                logGroupName=log_group_name,
                logStreamName=log_stream_name
            )
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                print(f"Creating Stream: {log_stream_name} Succeed")
                return True
            else:
                print(f"Creating Stream: {log_stream_name} Failed, Status {response['ResponseMetadata']['HTTPStatusCode']}")

        except Exception as e:
            print(f"Create Stream err: {e}")

    # Create unsuccessful
    exit(-1)


def handler(log):
    # response = client.get_log_events(
    #     logGroupName='auctionScraper',
    #     logStreamName='ApplicationLogs',
    #     limit=1,
    # )
    #
    # print(response)

    global seq_token
    global log_stream_name
    global log_group_name

    try:
        for i in range(3):
            log_event = {
                'logGroupName': log_group_name,
                'logStreamName': log_stream_name,
                'logEvents': [
                    {
                        'timestamp': int(round(time.time() * 1000)),
                        'message': log
                    },
                ],
            }

            if seq_token:
                log_event['sequenceToken'] = seq_token

            try:
                client.put_log_events(**log_event)

                # Put log to cloudWatch Succeed
                break

            except client.exceptions.InvalidSequenceTokenException as e:
                if 'The given sequenceToken is invalid' in str(e):
                    seq_token = re.search(r'The next expected sequenceToken is: (\d+)$', str(e)).group(1)

            except client.exceptions.DataAlreadyAcceptedException as e:
                if 'The given sequenceToken is invalid' in str(e):
                    seq_token = re.search(r'The next expected sequenceToken is: (\d+)$', str(e)).group(1)

    except Exception as e:
        print(f"----------------------- {e}")

    # print(response)


if __name__ == '__main__':
    init_stream()
    handler('nihao')
"""Lambda for ingesting EC2 State Change CloudWatch Events"""
import json
import logging
import os
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Any, List

import boto3
import botostubs
from datadog import initialize, api
from amplify_aws_utils.resource_helper import boto3_tags_to_dict, throttled_call
from amplify_aws_utils.clients.sts import STS
from dateutil.parser import parse

logger = logging.getLogger(__name__)


def handler(event, _):
    """
    Lambda Handler
    :param event: CloudWatch Event for EC2 State Change
    """
    logger.info("Event: %s", json.dumps(event))

    ssm_client: botostubs.SSM = boto3.client("ssm")
    initialize(
        api_key=ssm_client.get_parameter(
            Name="/account/app_auth/datadog/api_key",
            WithDecryption=True,
        )["Parameter"]["Value"],
        app_key=ssm_client.get_parameter(
            Name="/account/app_auth/datadog/flappy_detector_app_key",
            WithDecryption=True,
        )["Parameter"]["Value"],
    )
    ingestor = Ingestor(
        sts_client=STS(sts_client=boto3.client("sts")),
        datadog_client=api,
        dynamodb_table=boto3.resource('dynamodb').Table(os.environ["FLAPPY_DETECTOR_EC2_TABLE"]),
    )

    ingestor.ingest_events(
        events=[
            json.loads(record["Sns"]["Message"])
            for record in event["Records"]
        ]
    )


class Ingestor:
    """Class for ingesting events and storing them"""

    def __init__(
            self,
            sts_client: STS,
            datadog_client: api,
            dynamodb_table: botostubs.DynamoDB.DynamodbResource.Table,
    ):
        self.sts_client = sts_client
        self.datadog_client = datadog_client
        self.dynamodb_table = dynamodb_table

    def ingest_events(
            self,
            events: List[Dict[str, Any]],
    ):
        events_by_account = self._group_events(events=events)
        events_with_metadata = self._find_metadata(grouped_events=events_by_account)

        self._write_to_dynamodb(events=events_with_metadata)
        self._write_to_datadog(events=events_with_metadata)

    def _group_events(
            self,
            events: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        grouped_events = defaultdict(lambda: defaultdict(list))
        for event in events:
            grouped_events[event["account"]][event["region"]].append(
                {
                    "instance_id": event["detail"]["instance-id"],
                    "state": event["detail"]["state"],
                    "timestamp": Decimal(parse(event["time"]).timestamp()),
                    "region": event["region"],
                    "account": event["account"],
                }
            )

        return grouped_events

    def _find_metadata(
            self,
            grouped_events: Dict[str, Dict[str, List[Dict[str, str]]]],
    ) -> List[Dict[str, str]]:
        events_with_metadata = []
        for account, events_by_region in grouped_events.items():
            for region, events in events_by_region.items():
                ec2_client: botostubs.EC2 = self.sts_client.get_boto3_client_for_account(
                    account_id=account,
                    role_name=os.environ["FLAPPY_DETECTOR_ROLE"],
                    client_name="ec2",
                    region_name=region,
                )

                response = throttled_call(
                    ec2_client.describe_instances,
                    InstanceIds=[event["instance_id"] for event in events],
                )

                instance_metadata = {
                    instance["InstanceId"]: boto3_tags_to_dict(instance["Tags"])
                    for reservation in response["Reservations"]
                    for instance in reservation["Instances"]
                }

                for event in events:
                    cur_metadata = instance_metadata[event["instance_id"]]
                    standardized_tags = {
                        "application": cur_metadata.get("application"),
                        "environment": cur_metadata.get("environment") or cur_metadata.get("env"),
                        "team": cur_metadata.get("team"),
                    }
                    events_with_metadata.append(
                        dict(
                            **standardized_tags,
                            **event,
                        )
                    )

        return events_with_metadata

    def _write_to_dynamodb(
            self,
            events: List[Dict[str, str]],
    ):
        for event in events:
            throttled_call(
                self.dynamodb_table.put_item,
                Item=event,
            )

    def _write_to_datadog(
            self,
            events: List[Dict[str, str]],
    ):
        self.datadog_client.Metric.send(
            metrics=[
                {
                    "metric": "flappy_detector.churn",
                    "points": [
                        (
                            float(event["timestamp"]),
                            -1 if event["state"] == "terminated" else 1,
                        )
                    ],
                    "tags": [
                        f"{key}:{value}"
                        for key, value in event.items()
                    ],
                    "type": "gauge",
                }
                for event in events
            ]
        )

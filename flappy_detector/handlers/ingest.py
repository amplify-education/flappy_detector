"""Lambda for ingesting EC2 State Change CloudWatch Events"""
import json
import logging
import os
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Any, List

import boto3
import botostubs
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

    ingestor = Ingestor(
        sts_client=STS(sts_client=boto3.client("sts")),
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
            dynamodb_table: botostubs.DynamoDB.DynamodbResource.Table,
    ):
        """
        :param sts_client: STS Client for assuming roles.
        :param dynamodb_table: Table resource for our data store.
        """
        self.sts_client = sts_client
        self.dynamodb_table = dynamodb_table

    def ingest_events(
            self,
            events: List[Dict[str, Any]],
    ):
        """
        Ingests CloudWatch Events for EC2 state changes
        :param events: List of CloudWatch events.
        """
        grouped_events = self._group_events(events=events)
        events_with_metadata = self._find_metadata(grouped_events=grouped_events)

        self._write_to_dynamodb(events=events_with_metadata)

    def _group_events(
            self,
            events: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Groups the incoming CloudWatch events by account and region.
        :param events: The CloudWatch events in a flat list.
        :return: The CloudWatch events grouped first by account, then by region.
        """
        grouped_events: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
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
        """
        Look up metadata on each event.
        :param grouped_events: List of CloudWatch events grouped by account and region.
        :return: A list of records with metadata formatted for upload to DynamoDB.
        """
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

                    group_name = cur_metadata.get(
                        "spotinst:aws:ec2:group:id",
                        cur_metadata.get("aws:autoscaling:groupName"),
                    )

                    if not group_name:
                        logger.warning(
                            "Event for instance_id:%s has no associated group, ignoring",
                            event["instance_id"],
                            extra={
                                "instance_id": event["instance_id"],
                                "event": event,
                                "metadata": cur_metadata,
                            },
                        )
                        continue

                    standardized_tags = {
                        "application": cur_metadata.get("application"),
                        "environment":
                            cur_metadata.get("environment") or
                            cur_metadata.get("env"),
                        "team": cur_metadata.get("team"),
                        "group_name": group_name,
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
        """
        Writes the list of records to DynamoDB.
        :param events: List of records.
        """
        for event in events:
            throttled_call(
                self.dynamodb_table.put_item,
                Item=event,
            )

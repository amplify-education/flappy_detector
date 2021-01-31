"""Lambda for detecting whether or not resources are flapping"""
import json
import logging
import os
from datetime import timedelta, datetime
from decimal import Decimal
from typing import Dict, Any, List

import boto3
import botostubs
from amplify_aws_utils.resource_helper import get_boto3_paged_results
from boto3.dynamodb.conditions import Attr
from datadog import initialize, api

from flappy_detector.models import FlappyEvent

logger = logging.getLogger(__name__)


def handler(event, _):
    """Sample handler"""
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
    flappy_detector = FlappyDetector(
        datadog_client=api,
        dynamodb_table=boto3.resource('dynamodb').Table(os.environ["FLAPPY_DETECTOR_EC2_TABLE"]),
        max_event_age=timedelta(minutes=int(os.environ["FLAPPY_DETECTOR_MAX_EVENT_AGE_IN_MINS"])),
        min_number_of_events=int(os.environ["FLAPPY_DETECTOR_MIN_NUM_EVENTS"]),
        min_spread=int(os.environ["FLAPPY_DETECTOR_MIN_SPREAD"]),
    )

    flappy_detector.detect_flaps()


class FlappyDetector:
    """Class for detecting flappy resources"""

    def __init__(
            self,
            datadog_client: api,
            dynamodb_table: botostubs.DynamoDB.DynamodbResource.Table,
            max_event_age: timedelta,
            min_number_of_events: int,
            min_spread: int,
    ):
        self.datadog_client = datadog_client
        self.dynamodb_table = dynamodb_table
        self.max_event_age = max_event_age
        self.min_number_of_events = min_number_of_events
        self.min_spread = min_spread

    def detect_flaps(self):
        events = self._get_events(max_event_age=self.max_event_age)
        flapping_events = self._find_flapping_events(events=events)
        self._send_alerts(flapping_events=flapping_events)

    def _get_events(self, max_event_age: timedelta) -> List[Dict[str, Any]]:
        cut_off = Decimal((datetime.now() - max_event_age).timestamp())
        return get_boto3_paged_results(
            self.dynamodb_table.scan,
            results_key="Items",
            next_token_key="LastEvaluatedKey",
            next_request_token_key="ExclusiveStartKey",
            FilterExpression=(Attr("timestamp").gte(cut_off)),
            ConsistentRead=True,
        )

    def _find_flapping_events(self, events: List[Dict[str, Any]]) -> List[FlappyEvent]:
        flappy_events = {}

        for event in events:
            flappy_event = FlappyEvent(
                account=event["account"],
                region=event["region"],
                environment=event["environment"],
                application=event["application"],
            )
            flappy_event = flappy_events.get(flappy_event.key, flappy_event)
            if not flappy_event.team:
                flappy_event.team = event.get("team")

            flappy_event.count += 1
            flappy_event.spread += -1 if event["state"] == "terminated" else 1

            flappy_events[flappy_event.key] = flappy_event

        return [
            flappy_event
            for flappy_event in flappy_events.values()
            if flappy_event.count >= self.min_number_of_events and
               abs(flappy_event.spread) <= self.min_spread
        ]

    def _send_alerts(self, flapping_events: List[FlappyEvent]):
        if not flapping_events:
            return

        logger.info(
            "Sending flappy events",
            extra={"flapping_apps": flapping_events},
        )

        for event in flapping_events:
            self.datadog_client.Event.create(
                title=f"Flappy Detector: {event.application} might be flapping in {event.environment}",
                text="%%% \nThis application might be flapping.\n"
                     f"There have been {event.count} starts/stops, "
                     f"but the total number of instances has only changed by {event.spread}.\n"
                     "Please investigate:\n"
                     "  * Scaling might be configured too aggressively\n"
                     "  * New instances are failing to start\n"
                     "  * Host is undersized and failing under load\n %%%",
                alert_type="warning",
                aggregation_key=event.key,
                tags=event.tags,
                attach_host_name=False,
            )

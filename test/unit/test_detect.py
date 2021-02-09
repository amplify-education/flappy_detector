"""Tests for the Detect lambda"""
from decimal import Decimal
from datetime import timedelta, datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch, call, ANY

from boto3.dynamodb.conditions import Attr

from flappy_detector.handlers.detect import FlappyDetector, handler
from flappy_detector.models import FlappyEvent
from flappy_detector.utils.enum import Ec2State


MOCK_TEAM = "MOCK_TEAM"
MOCK_GROUP_NAME = "MOCK_GROUP_NAME"
MOCK_GROUP_NAME_SCALE_UP = "MOCK_GROUP_NAME_SCALE_UP"
MOCK_GROUP_NAME_SCALE_DOWN = "MOCK_GROUP_NAME_SCALE_DOWN"
MOCK_APPLICATION_SCALE_UP = "MOCK_APPLICATION_SCALE_UP"
MOCK_APPLICATION_SCALE_DOWN = "MOCK_APPLICATION_SCALE_DOWN"
MOCK_APPLICATION_FLAPPY = "MOCK_APPLICATION_FLAPPY"
MOCK_ENVIRONMENT = "MOCK_ENVIRONMENT"
MOCK_REGION = "MOCK_REGION"
MOCK_ACCOUNT = "MOCK_ACCOUNT"
MOCK_EC2_TABLE = "MOCK_FLAPPY_DETECTOR_EC2_TABLE"
MOCK_MAX_EVENT_AGE_IN_MINS = 120
MOCK_MIN_NUM_EVENTS = 4
MOCK_MIN_SPREAD = 2
ENVIRONMENT_VARIABLES = {
    "FLAPPY_DETECTOR_EC2_TABLE": str(MOCK_EC2_TABLE),
    "FLAPPY_DETECTOR_MAX_EVENT_AGE_IN_MINS": str(MOCK_MAX_EVENT_AGE_IN_MINS),
    "FLAPPY_DETECTOR_MIN_NUM_EVENTS": str(MOCK_MIN_NUM_EVENTS),
    "FLAPPY_DETECTOR_MIN_SPREAD": str(MOCK_MIN_SPREAD),
}
MOCK_TIME_NOW = datetime(2020, 1, 1)


@patch.dict("os.environ", ENVIRONMENT_VARIABLES)
class TestHandlerDetect(TestCase):
    """Tests for the Detect lambda"""

    def setUp(self) -> None:
        self.datadog_client = MagicMock()
        self.dynamodb_table = MagicMock()
        self.max_event_age = timedelta(minutes=MOCK_MAX_EVENT_AGE_IN_MINS)
        self.min_number_of_events = MOCK_MIN_NUM_EVENTS
        self.min_spread = MOCK_MIN_SPREAD

        self.handler = FlappyDetector(
            datadog_client=self.datadog_client,
            dynamodb_table=self.dynamodb_table,
            max_event_age=self.max_event_age,
            min_number_of_events=self.min_number_of_events,
            min_spread=self.min_spread,
        )

    @patch("flappy_detector.handlers.detect.FlappyDetector")
    @patch("boto3.client")
    @patch("boto3.resource")
    def test_handler(self, mock_boto3_resource, mock_boto3_client, mock_flappy_detector):
        """Tests the Detect lambda handler function"""
        handler({}, None)

        mock_boto3_client.return_value.get_parameter.assert_has_calls(
            calls=[
                call(
                    Name="/account/app_auth/datadog/api_key",
                    WithDecryption=True,
                ),
                call(
                    Name="/account/app_auth/datadog/flappy_detector_app_key",
                    WithDecryption=True,
                ),
            ],
            any_order=True,
        )
        mock_boto3_resource.return_value.Table.assert_called_once_with(MOCK_EC2_TABLE)
        mock_flappy_detector.assert_called_once_with(
            datadog_client=ANY,
            dynamodb_table=mock_boto3_resource.return_value.Table.return_value,
            max_event_age=timedelta(minutes=MOCK_MAX_EVENT_AGE_IN_MINS),
            min_number_of_events=MOCK_MIN_NUM_EVENTS,
            min_spread=MOCK_MIN_SPREAD,
        )
        mock_flappy_detector.return_value.detect_flaps.assert_called_once()

    def test_detect_flaps(self):
        """Tests Detect detect_flaps"""
        self.handler._get_events = MagicMock()
        self.handler._find_flapping_events = MagicMock()
        self.handler._send_alerts = MagicMock()

        self.handler.detect_flaps()

        self.handler._get_events.assert_called_once_with()
        self.handler._find_flapping_events.assert_called_once_with(
            events=self.handler._get_events.return_value,
        )
        self.handler._send_alerts.assert_called_once_with(
            flapping_events=self.handler._find_flapping_events.return_value,
        )

    @patch("flappy_detector.handlers.detect.datetime", MagicMock(now=lambda: MOCK_TIME_NOW))
    def test_get_events(self):
        """Tests Detect get_events"""
        mock_item = {}
        self.dynamodb_table.scan.return_value = {
            "Items": [mock_item]
        }

        events = self.handler._get_events()

        self.assertEqual(
            events,
            [mock_item],
        )
        self.dynamodb_table.scan.assert_called_once_with(
            FilterExpression=(
                Attr("timestamp").gte(Decimal((MOCK_TIME_NOW - self.max_event_age).timestamp()))
            ),
            ConsistentRead=True,
        )

    def test_find_flapping_events(self):
        """Test Detect find_flapping_events"""
        base_event = {
            "account": MOCK_ACCOUNT,
            "region": MOCK_REGION,
            "environment": MOCK_ENVIRONMENT,
            "group_name": MOCK_GROUP_NAME,
        }

        events = [
            {
                **base_event,
                **{
                    "application": MOCK_APPLICATION_SCALE_DOWN,
                    "state": Ec2State.TERMINATED.value,
                }
            }
            for _ in range(10)
        ] + [
            {
                **base_event,
                **{
                    "application": MOCK_APPLICATION_SCALE_UP,
                    "state": Ec2State.RUNNING.value,
                }
            }
            for _ in range(10)
        ] + [
            {
                **base_event,
                **{
                    "application": MOCK_APPLICATION_FLAPPY,
                    "state": state,
                }
            }
            for state in [
                Ec2State.RUNNING,
                Ec2State.TERMINATED,
                Ec2State.RUNNING,
                Ec2State.TERMINATED,
                Ec2State.RUNNING,
                Ec2State.TERMINATED,
            ]
        ]

        actual = self.handler._find_flapping_events(events=events)
        self.assertEqual(
            actual,
            [
                FlappyEvent(
                    account=MOCK_ACCOUNT,
                    region=MOCK_REGION,
                    environment=MOCK_ENVIRONMENT,
                    application=MOCK_APPLICATION_FLAPPY,
                    group_name=MOCK_GROUP_NAME,
                    count=6,
                    spread=0,
                )
            ]
        )

    def test_find_flapping_events_by_group(self):
        """Test Detect find_flapping_events separated by group"""
        base_event = {
            "account": MOCK_ACCOUNT,
            "region": MOCK_REGION,
            "environment": MOCK_ENVIRONMENT,
            "application": MOCK_APPLICATION_FLAPPY,
        }

        events = [
            {
                **base_event,
                **{
                    "group_name": MOCK_GROUP_NAME_SCALE_DOWN,
                    "state": Ec2State.TERMINATED.value,
                }
            }
            for _ in range(10)
        ] + [
            {
                **base_event,
                **{
                    "group_name": MOCK_GROUP_NAME_SCALE_UP,
                    "state": Ec2State.RUNNING.value,
                }
            }
            for _ in range(10)
        ] + [
            {
                **base_event,
                **{
                    "group_name": MOCK_GROUP_NAME,
                    "state": state,
                }
            }
            for state in [
                Ec2State.RUNNING,
                Ec2State.TERMINATED,
                Ec2State.RUNNING,
                Ec2State.TERMINATED,
                Ec2State.RUNNING,
                Ec2State.TERMINATED,
            ]
        ]

        actual = self.handler._find_flapping_events(events=events)
        self.assertEqual(
            actual,
            [
                FlappyEvent(
                    account=MOCK_ACCOUNT,
                    region=MOCK_REGION,
                    environment=MOCK_ENVIRONMENT,
                    application=MOCK_APPLICATION_FLAPPY,
                    group_name=MOCK_GROUP_NAME,
                    count=6,
                    spread=0,
                )
            ]
        )

    def test_find_flapping_events_malformed(self):
        """Test Detect find_flapping_events with malformed event"""
        events = [
            {
                "account": MOCK_ACCOUNT,
                "region": MOCK_REGION,
                "environment": MOCK_ENVIRONMENT,
                "application": None,
                "group_name": MOCK_GROUP_NAME,
            }
        ]

        actual = self.handler._find_flapping_events(events=events)
        self.assertEqual(
            actual,
            []
        )

    def test_find_flapping_events_team(self):
        """Test Detect find_flapping_events with initially missing team"""
        events = [
            {
                "account": MOCK_ACCOUNT,
                "region": MOCK_REGION,
                "environment": MOCK_ENVIRONMENT,
                "application": MOCK_APPLICATION_FLAPPY,
                "group_name": MOCK_GROUP_NAME,
                "state": Ec2State.TERMINATED.value,
            },
            {
                "account": MOCK_ACCOUNT,
                "region": MOCK_REGION,
                "environment": MOCK_ENVIRONMENT,
                "application": MOCK_APPLICATION_FLAPPY,
                "group_name": MOCK_GROUP_NAME,
                "state": Ec2State.RUNNING.value,
                "team": MOCK_TEAM,
            },
            {
                "account": MOCK_ACCOUNT,
                "region": MOCK_REGION,
                "environment": MOCK_ENVIRONMENT,
                "application": MOCK_APPLICATION_FLAPPY,
                "group_name": MOCK_GROUP_NAME,
                "state": Ec2State.TERMINATED.value,
            },
            {
                "account": MOCK_ACCOUNT,
                "region": MOCK_REGION,
                "environment": MOCK_ENVIRONMENT,
                "application": MOCK_APPLICATION_FLAPPY,
                "group_name": MOCK_GROUP_NAME,
                "state": Ec2State.RUNNING.value,
            },
        ]

        actual = self.handler._find_flapping_events(events=events)
        self.assertEqual(
            actual,
            [
                FlappyEvent(
                    account=MOCK_ACCOUNT,
                    region=MOCK_REGION,
                    environment=MOCK_ENVIRONMENT,
                    application=MOCK_APPLICATION_FLAPPY,
                    group_name=MOCK_GROUP_NAME,
                    team=MOCK_TEAM,
                    count=4,
                    spread=0,
                )
            ],
        )

    def test_send_alerts(self):
        """Test Detect send alerts"""
        events = [
            FlappyEvent(
                account=MOCK_ACCOUNT,
                region=MOCK_REGION,
                environment=MOCK_ENVIRONMENT,
                application=MOCK_APPLICATION_FLAPPY,
                group_name=MOCK_GROUP_NAME,
                team=MOCK_TEAM,
                count=6,
                spread=0,
            ),
            FlappyEvent(
                account=MOCK_ACCOUNT,
                region=MOCK_REGION,
                environment=MOCK_ENVIRONMENT,
                application=MOCK_APPLICATION_FLAPPY,
                group_name=MOCK_GROUP_NAME,
                team=MOCK_TEAM,
                count=6,
                spread=0,
            ),
        ]

        self.handler._send_alerts(flapping_events=events)

        self.datadog_client.Event.create.assert_has_calls(
            calls=[
                call(
                    title=ANY,
                    text=ANY,
                    alert_type="warning",
                    aggregation_key=event.key,
                    tags=event.tags,
                    attach_host_name=False,
                )
                for event in events
            ]
        )

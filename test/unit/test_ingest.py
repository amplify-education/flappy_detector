"""Tests for the Ingest lambda"""
import json
from decimal import Decimal
from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch, call, ANY

from amplify_aws_utils.resource_helper import dict_to_boto3_tags

from flappy_detector.handlers.ingest import Ingestor, handler
from flappy_detector.utils.enum import Ec2State


MOCK_GROUP_NAME = "MOCK_GROUP_NAME"
MOCK_INSTANCE_ID = "MOCK_INSTANCE_ID"
MOCK_TEAM = "MOCK_TEAM"
MOCK_APPLICATION_FLAPPY = "MOCK_APPLICATION_FLAPPY"
MOCK_ENVIRONMENT = "MOCK_ENVIRONMENT"
MOCK_REGION = "MOCK_REGION"
MOCK_ACCOUNT = "MOCK_ACCOUNT"
MOCK_EC2_TABLE = "MOCK_FLAPPY_DETECTOR_EC2_TABLE"
MOCK_ROLE = "MOCK_FLAPPY_DETECTOR_ROLE"
ENVIRONMENT_VARIABLES = {
    "FLAPPY_DETECTOR_EC2_TABLE": str(MOCK_EC2_TABLE),
    "FLAPPY_DETECTOR_ROLE": MOCK_ROLE,
}
MOCK_TIME_NOW = datetime(2020, 1, 1)


@patch.dict("os.environ", ENVIRONMENT_VARIABLES)
class TestHandlerIngest(TestCase):
    """Tests for the Ingest lambda"""

    def setUp(self) -> None:
        self.sts_client = MagicMock()
        self.dynamodb_table = MagicMock()

        self.handler = Ingestor(
            sts_client=self.sts_client,
            dynamodb_table=self.dynamodb_table,
        )

    @patch("flappy_detector.handlers.ingest.STS")
    @patch("flappy_detector.handlers.ingest.Ingestor")
    @patch("boto3.client")
    @patch("boto3.resource")
    def test_handler(self, mock_boto3_resource, mock_boto3_client, mock_ingestor, mock_sts):
        """Tests the Ingest lambda handler function"""
        mock_event = {}
        handler(
            {
                "Records": [
                    {
                        "Sns": {
                            "Message": json.dumps(mock_event)
                        }
                    },
                ]
            },
            None,
        )

        mock_boto3_client.assert_called_once_with("sts")
        mock_sts.assert_called_once_with(
            sts_client=mock_boto3_client.return_value,
        )
        mock_boto3_resource.return_value.Table.assert_called_once_with(MOCK_EC2_TABLE)
        mock_ingestor.assert_called_once_with(
            sts_client=ANY,
            dynamodb_table=mock_boto3_resource.return_value.Table.return_value,
        )
        mock_ingestor.return_value.ingest_events.assert_called_once_with(events=[mock_event])

    def test_ingest_events(self):
        """Test Ingest ingest_events"""
        mock_event = {}
        self.handler._group_events = MagicMock()
        self.handler._find_metadata = MagicMock()
        self.handler._write_to_dynamodb = MagicMock()

        self.handler.ingest_events(events=[mock_event])

        self.handler._group_events.assert_called_once_with(
            events=[mock_event],
        )
        self.handler._find_metadata.assert_called_once_with(
            grouped_events=self.handler._group_events.return_value,
        )
        self.handler._write_to_dynamodb.assert_called_once_with(
            events=self.handler._find_metadata.return_value,
        )

    def test_group_events(self):
        """Test Ingest group_events"""
        mock_events = [
            {
                "region": MOCK_REGION,
                "account": MOCK_ACCOUNT,
                "time": MOCK_TIME_NOW.isoformat(),
                "detail": {
                    "instance-id": MOCK_INSTANCE_ID,
                    "state": Ec2State.TERMINATED.value,
                }
            }
        ]
        expected = {
            MOCK_ACCOUNT: {
                MOCK_REGION: [
                    {
                        "state": Ec2State.TERMINATED.value,
                        "timestamp": Decimal(MOCK_TIME_NOW.timestamp()),
                        "instance_id": MOCK_INSTANCE_ID,
                    },
                ]
            },
        }

        actual = self.handler._group_events(events=mock_events)

        self.assertEqual(
            actual,
            expected,
        )

    def test_find_metadata_eg(self):
        """Test Ingest find_metadata for EGs"""
        mock_events = {
            MOCK_ACCOUNT: {
                MOCK_REGION: [
                    {
                        "state": Ec2State.TERMINATED.value,
                        "timestamp": Decimal(MOCK_TIME_NOW.timestamp()),
                        "instance_id": MOCK_INSTANCE_ID,
                    },
                ]
            },
        }
        ec2_client = self.sts_client.get_boto3_client_for_account.return_value
        ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": MOCK_INSTANCE_ID,
                            "Tags": dict_to_boto3_tags(
                                {
                                    "application": MOCK_APPLICATION_FLAPPY,
                                    "environment": MOCK_ENVIRONMENT,
                                    "team": MOCK_TEAM,
                                    "spotinst:aws:ec2:group:id": MOCK_GROUP_NAME,
                                }
                            )
                        }
                    ]
                }
            ]
        }
        expected = [
            {
                "account": MOCK_ACCOUNT,
                "region": MOCK_REGION,
                "state": Ec2State.TERMINATED.value,
                "timestamp": Decimal(MOCK_TIME_NOW.timestamp()),
                "instance_id": MOCK_INSTANCE_ID,
                "application": MOCK_APPLICATION_FLAPPY,
                "group_name": MOCK_GROUP_NAME,
                "environment": MOCK_ENVIRONMENT,
                "team": MOCK_TEAM,
            }
        ]

        actual = self.handler._find_metadata(grouped_events=mock_events)

        self.assertEqual(
            actual,
            expected,
        )
        self.sts_client.get_boto3_client_for_account.assert_called_once_with(
            account_id=MOCK_ACCOUNT,
            role_name=MOCK_ROLE,
            client_name="ec2",
            region_name=MOCK_REGION,
        )
        ec2_client.describe_instances.assert_called_once_with(
            InstanceIds=[MOCK_INSTANCE_ID],
        )

    def test_find_metadata_asg(self):
        """Test Ingest find_metadata for ASGs"""
        mock_events = {
            MOCK_ACCOUNT: {
                MOCK_REGION: [
                    {
                        "state": Ec2State.TERMINATED.value,
                        "timestamp": Decimal(MOCK_TIME_NOW.timestamp()),
                        "instance_id": MOCK_INSTANCE_ID,
                    },
                ]
            },
        }
        ec2_client = self.sts_client.get_boto3_client_for_account.return_value
        ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": MOCK_INSTANCE_ID,
                            "Tags": dict_to_boto3_tags(
                                {
                                    "application": MOCK_APPLICATION_FLAPPY,
                                    "environment": MOCK_ENVIRONMENT,
                                    "team": MOCK_TEAM,
                                    "aws:autoscaling:groupName": MOCK_GROUP_NAME,
                                }
                            )
                        }
                    ]
                }
            ]
        }
        expected = [
            {
                "account": MOCK_ACCOUNT,
                "region": MOCK_REGION,
                "state": Ec2State.TERMINATED.value,
                "timestamp": Decimal(MOCK_TIME_NOW.timestamp()),
                "instance_id": MOCK_INSTANCE_ID,
                "application": MOCK_APPLICATION_FLAPPY,
                "group_name": MOCK_GROUP_NAME,
                "environment": MOCK_ENVIRONMENT,
                "team": MOCK_TEAM,
            }
        ]

        actual = self.handler._find_metadata(grouped_events=mock_events)

        self.assertEqual(
            actual,
            expected,
        )
        self.sts_client.get_boto3_client_for_account.assert_called_once_with(
            account_id=MOCK_ACCOUNT,
            role_name=MOCK_ROLE,
            client_name="ec2",
            region_name=MOCK_REGION,
        )
        ec2_client.describe_instances.assert_called_once_with(
            InstanceIds=[MOCK_INSTANCE_ID],
        )

    def test_find_metadata_no_group(self):
        """Test Ingest find_metadata with no group"""
        mock_events = {
            MOCK_ACCOUNT: {
                MOCK_REGION: [
                    {
                        "state": Ec2State.TERMINATED.value,
                        "timestamp": Decimal(MOCK_TIME_NOW.timestamp()),
                        "instance_id": MOCK_INSTANCE_ID,
                    },
                ]
            },
        }
        ec2_client = self.sts_client.get_boto3_client_for_account.return_value
        ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": MOCK_INSTANCE_ID,
                            "Tags": dict_to_boto3_tags(
                                {
                                    "application": MOCK_APPLICATION_FLAPPY,
                                    "environment": MOCK_ENVIRONMENT,
                                    "team": MOCK_TEAM,
                                }
                            )
                        }
                    ]
                }
            ]
        }
        expected = []

        actual = self.handler._find_metadata(grouped_events=mock_events)

        self.assertEqual(
            actual,
            expected,
        )
        self.sts_client.get_boto3_client_for_account.assert_called_once_with(
            account_id=MOCK_ACCOUNT,
            role_name=MOCK_ROLE,
            client_name="ec2",
            region_name=MOCK_REGION,
        )
        ec2_client.describe_instances.assert_called_once_with(
            InstanceIds=[MOCK_INSTANCE_ID],
        )

    def test_write_to_dynamodb(self):
        """Test Ingest write_to_dynamodb"""
        mock_events = [
            {"foo": "bar"},
            {"baz": "buzz"},
        ]

        self.handler._write_to_dynamodb(events=mock_events)

        self.dynamodb_table.put_item.assert_has_calls(
            calls=[
                call(Item=event)
                for event in mock_events
            ]
        )

"""For package documentation, see README"""
import logging
import os

from amplify_python_logging.amplify_logging import init_logging
from aws_xray_sdk.core import patch_all
from aws_xray_sdk.core import xray_recorder

xray_recorder.configure(
    context_missing='LOG_ERROR',
)

patch_all()

init_logging(json_logging=True, log_level=os.environ.get('LOG_LEVEL', logging.INFO))

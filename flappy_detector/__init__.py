"""For package documentation, see README"""
import logging
import os
from distutils.util import strtobool

from amplify_python_logging.amplify_logging import init_logging
from aws_xray_sdk.core import patch_all
from aws_xray_sdk.core import xray_recorder

xray_recorder.configure(
    context_missing='LOG_ERROR',
)

patch_all()

init_logging(
    json_logging=strtobool(os.environ.get('JSON_LOGGING', 'True')),
    log_level=os.environ.get('LOG_LEVEL', logging.INFO),
    third_party_log_level=logging.ERROR,
)

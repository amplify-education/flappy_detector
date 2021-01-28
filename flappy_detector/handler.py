"""Sample lambda handler function"""
import logging

from amplify_python_logging.amplify_logging import set_trace_key


logger = logging.getLogger(__name__)
# pylint: disable=unused-argument
def hello(event, context):
    """Sample handler"""
    set_trace_key(lambda_context=context)

    logger.info("Event: %s", event)
    logger.info("Context: %s", vars(context))
    return "hello world"

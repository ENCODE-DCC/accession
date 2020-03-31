import logging
import sys

import encode_utils


def logger_factory(
    logger_name: str, log_file_path: str, no_log_file: bool = False
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")

    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)

    eu_debug_logger = logging.getLogger(encode_utils.DEBUG_LOGGER_NAME)
    for hdlr in eu_debug_logger.handlers:
        eu_debug_logger.removeHandler(hdlr)
    eu_debug_logger.addHandler(stdout_handler)

    eu_post_logger = logging.getLogger(encode_utils.POST_LOGGER_NAME)
    for hdlr in eu_post_logger.handlers:
        eu_post_logger.removeHandler(hdlr)
    eu_post_logger.addHandler(stdout_handler)

    if not no_log_file:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        eu_debug_logger.addHandler(file_handler)
        eu_post_logger.addHandler(file_handler)

    return logger

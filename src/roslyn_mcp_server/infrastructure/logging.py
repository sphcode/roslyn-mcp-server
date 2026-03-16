import logging
import os

LOGGER_NAME = "roslyn_mcp_server"


def configure_logging():
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    level_name = os.environ.get("ROSLYN_MCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            "%H:%M:%S",
        )
    )

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name):
    configure_logging()
    return logging.getLogger(name)

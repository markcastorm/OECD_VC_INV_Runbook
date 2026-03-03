# logger_setup.py
# Centralized logging configuration with timestamped log files

import os
import logging
import config


def setup_logging():
    """
    Set up logging with both console and file handlers.
    Creates a timestamped log file in the logs folder.
    Returns the root logger.
    """

    # Create log directory
    os.makedirs(config.LOG_DIR, exist_ok=True)

    # Generate log filename
    log_filename = config.LOG_FILE_PATTERN.format(timestamp=config.RUN_TIMESTAMP)
    log_file_path = os.path.join(config.LOG_DIR, log_filename)

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.LOG_LEVEL))

    # Remove any existing handlers
    logger.handlers = []

    # Shared formatter
    formatter = logging.Formatter(
        config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT
    )

    # Console handler
    if config.LOG_TO_CONSOLE:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, config.LOG_LEVEL))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if config.LOG_TO_FILE:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(getattr(logging, config.LOG_LEVEL))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in (
        'selenium',
        'selenium.webdriver',
        'urllib3',
        'urllib3.connectionpool',
        'undetected_chromedriver',
        'websocket',
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.info("=" * 60)
    logger.info("Logging initialized")
    logger.info(f"Log file      : {log_file_path}")
    logger.info(f"Log level     : {config.LOG_LEVEL}")
    logger.info(f"Run timestamp : {config.RUN_TIMESTAMP}")
    logger.info("=" * 60)

    return logger


if __name__ == '__main__':
    logger = setup_logging()
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")

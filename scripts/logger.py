import logging
import configparser

def setup_logger():
    """
    Sets up a centralized logger for the application.

    Reads the log file path from the configuration file and sets up a logger
    that writes to both the specified file and the console.

    Returns:
        logging.Logger: The configured logger instance.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    log_file = config.get('LOGGING', 'log_file', fallback='logs/strategy.log')

    # Create logger
    logger = logging.getLogger('trading_strategy')
    logger.setLevel(logging.INFO)

    # Create handlers if they don't exist already to avoid duplicate logs
    if not logger.handlers:
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Add the handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

# Create a global logger instance to be used by other modules
logger = setup_logger()

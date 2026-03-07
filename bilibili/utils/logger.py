import logging
import os

# Create logs directory if not exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

ERROR_LOG_FILE = os.path.join(LOG_DIR, 'error.log')

def setup_logger():
    """
    Sets up the logger. 
    Clears the error.log at the start of the process.
    """
    # Clear the error log file at the start
    with open(ERROR_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('')

    # Configure logging
    logger = logging.getLogger('bilibili_downloader')
    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter('%(levelname)s: %(message)s')
    ch.setFormatter(ch_formatter)

    # File handler for errors
    fh = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
    fh.setLevel(logging.ERROR)
    fh_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(fh_formatter)

    # Avoid adding duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger

logger = setup_logger()

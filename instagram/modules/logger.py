import logging
import os
from colorama import Fore, Style
from ..settings import LOG_DIR

def setup_logger():
    """Configure logging to file and console."""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Create a custom logger
    logger = logging.getLogger('instagram_downloader')
    logger.setLevel(logging.DEBUG)
    
    # Create handlers
    c_handler = logging.StreamHandler()
    f_handler = logging.FileHandler(os.path.join(LOG_DIR, 'debug.log'))
    c_handler.setLevel(logging.INFO)
    f_handler.setLevel(logging.DEBUG)
    
    # Create formatters and add it to handlers
    c_format = logging.Formatter('%(message)s')
    f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    c_handler.setFormatter(c_format)
    f_handler.setFormatter(f_format)
    
    # Add handlers to the logger
    if not logger.handlers:
        logger.addHandler(c_handler)
        logger.addHandler(f_handler)
    
    return logger

def log_info(logger, message, color=Fore.WHITE):
    """Log info with color support for console."""
    logger.info(f"{color}{message}{Style.RESET_ALL}")

def log_error(logger, message):
    """Log error with red color."""
    logger.error(f"{Fore.RED}ERROR: {message}{Style.RESET_ALL}")

def log_success(logger, message):
    """Log success with green color."""
    logger.info(f"{Fore.GREEN}{message}{Style.RESET_ALL}")

# modules/utils/logger_config.py
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

'''
| Level Name | Numeric Value | Used For                                    |
| ---------- | ------------- | ------------------------------------------- |
| `DEBUG`    | 10            | Detailed internal information for devs      |
| `INFO`     | 20            | General application events/status           |
| `WARNING`  | 30            | Minor issues or unexpected behavior         |
| `ERROR`    | 40            | Errors that prevent a function from running |
| `CRITICAL` | 50            | Major failures - app can't continue         |
'''

def setup_logger(
    name: str,
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: str = ".logs",
    filename_prefix: str = None,
    refresh_logs: bool = False,
    use_timestamp: bool = False,
    max_bytes: int = 2_000_000,
    backup_count: int = 3
) -> logging.Logger:
    """
    Creates and configures a logger with console and optional file output.

    Args:
        name (str): Name of the logger (usually __name__).
        level (str): Logging level as a string.
        log_to_file (bool): Whether to log to a file.
        log_dir (str): Directory to store logs.
        filename_prefix (str): Custom file prefix; defaults to module name.
        refresh_logs (bool): If True, overwrite logs on every run.
        use_timestamp (bool): If True, include timestamp in filename.
        max_bytes (int): Max file size before rotating.
        backup_count (int): Number of rotated backups to keep.

    Returns:
        logging.Logger: Configured logger.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # Avoid duplicate handlers

    level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_to_file:
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") if use_timestamp else ""
        prefix = filename_prefix or name.replace(".", "_")
        filename = f"{prefix}_{timestamp}.log" if timestamp else f"{prefix}.log"
        file_path = os.path.join(log_dir, filename)

        if refresh_logs:
            file_handler = logging.FileHandler(file_path, mode="w")
        else:
            file_handler = RotatingFileHandler(file_path, maxBytes=max_bytes, backupCount=backup_count)

        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

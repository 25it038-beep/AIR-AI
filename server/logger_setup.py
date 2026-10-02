import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_loggers(logs_dir: Path):
    """Initialize structured, dedicated log files for HS AI subsystems."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    def _create_logger(name: str, filename: str):
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        
        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        handler = RotatingFileHandler(
            logs_dir / filename,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    server_logger = _create_logger("hs_ai.server", "server.log")
    model_logger = _create_logger("hs_ai.model", "model.log")
    network_logger = _create_logger("hs_ai.network", "network.log")
    security_logger = _create_logger("hs_ai.security", "security.log")

    return {
        "server": server_logger,
        "model": model_logger,
        "network": network_logger,
        "security": security_logger
    }

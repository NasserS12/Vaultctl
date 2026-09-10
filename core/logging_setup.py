"""Central logging configuration.

Import this module once (main.py does it first) so every other module
can simply do `logger = logging.getLogger(__name__)` and inherit the
same file handler / format.
"""
import logging
import os

LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "diagnostic_tool.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("vaultctl")

import logging
from rich.logging import RichHandler
from rich import print

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

def getLogger(name: str):
    return logging.getLogger(name=name)

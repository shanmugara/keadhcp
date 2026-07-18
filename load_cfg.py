import configparser
import os

_CONFIG_PATHS = [
    os.path.join(os.path.dirname(__file__), "config.ini"),
    "/etc/keadhcp/config.ini",
]


def load_db_config():
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATHS)
    return cfg["mysql"]

def load_ddns_config():
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATHS)
    return cfg["ddns"]  

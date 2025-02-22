import codecs
import configparser
import importlib.metadata
import logging
import os
import sys

from pathlib import Path

log = logging.getLogger("util")

try:
    from docopt import docopt
except ImportError:
    log.error("ImportError: Please install docopt to use the DBus CLI.")

VERSION = importlib.metadata.version("blockify")
CONFIG = None
if "XDG_CONFIG_HOME" in os.environ:
    CONFIG_DIR = Path(os.environ["XDG_CONFIG_HOME"])/"blockify"
else:
    CONFIG_DIR = Path.home()/".config"/"blockify"
CONFIG_FILE = CONFIG_DIR/"blockify.ini"
BLOCKLIST_FILE = CONFIG_DIR/"blocklist.txt"

class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    From http://www.electricmonk.nl/log/2011/08/14/redirect-stdout-and-stderr-to-a-logger-in-python/
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


def init_logger(logpath: Path|str=None, loglevel=0, quiet=False):
    """Initializes the logging module."""
    logger = logging.getLogger()

    # Cap loglevel at 3 to avoid index errors.
    if loglevel > 3:
        loglevel = 3
    levels = [logging.ERROR, logging.WARN, logging.INFO, logging.DEBUG]
    logger.setLevel(levels[loglevel])

    logformat = "%(asctime)-14s %(levelname)-8s %(name)-8s %(message)s"

    formatter = logging.Formatter(logformat, "%Y-%m-%d %H:%M:%S")

    if not quiet:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        log.debug("Added logging console handler.")
        log.info("Loglevel is {} (10=DEBUG, 20=INFO, 30=WARN).".format(levels[loglevel]))

        # Redirect all stderr to a logger so that we can capture it in the logfile.
        stderr_logger = logging.getLogger("stderr")
        stream_logger = StreamToLogger(stderr_logger, logging.ERROR)
        sys.stderr = stream_logger
    if logpath:
        try:
            logfile = Path(logpath).resolve()
            file_handler = logging.FileHandler(logfile)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            log.debug("Added logging file handler: {}.".format(logfile))
        except IOError:
            log.error("Could not attach file handler.")


def init_config_dir():
    """Determine if a config dir for blockify exists and if not, create it."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=False)
        log.info("Created config directory %s.", CONFIG_DIR)

    if not CONFIG_FILE.is_file():
        save_options(CONFIG_FILE, default_options())


def default_options() -> dict:
    return {
        "general": {
            "autodetect": True,
            "automute": True,
            "autoplay": True,
            "substring_search": False,
            "start_spotify": True,
            "detach_spotify": False,
            "use_window_title": True
        },
        "cli": {
            "update_interval": 350,
            "unmute_delay": 700
        },
    }


def load_options():
    log.info("Loading configuration.")
    options = default_options()
    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_FILE)
    except Exception as e:
        log.warning("Could not read config file: {}. Using default options.".format(e))
    else:
        for section_name, section_value in options.items():
            for option_name, option_value in section_value.items():
                option = read_option(config, section_name, option_name, option_value,
                                     options[section_name][option_name])
                if option is not None:
                    options[section_name][option_name] = option
        log.info("Configuration loaded.")

    return options


def read_option(config, section_name, option_name, option_value, default_option_value):
    option = None
    try:
        if isinstance(option_value, bool):
            option = config.getboolean(section_name, option_name)
        elif isinstance(option_value, int):
            option = config.getint(section_name, option_name)
        else:
            option = config.get(section_name, option_name)
    except Exception:
        log.warning("Could not parse option %s for section %s. Using default value %s.", option_name, section_name,
                 default_option_value)

    return option


def save_options(config_file: Path, options: dict):
    config = configparser.ConfigParser()
    # Write out the sections in this order. Using options keys would be unpredictable.
    sections = ["general", "cli"]
    for section in sections:
        config.add_section(section)
        for k, v in options[section].items():
            config.set(section, k, str(v))

    with codecs.open(config_file, "w", encoding="utf-8") as f:
        config.write(f)

    log.info("Configuration written to {}.".format(config_file))


def initialize(args):
    if args:
        init_logger(args["--log"], args["-v"], args["--quiet"])
    else:
        init_logger()

    # Set up the configuration directory & files, if necessary.
    init_config_dir()

    global CONFIG
    CONFIG = load_options()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Duallog

This module contains a function "setup()" that sets up dual logging. 
All subsequent log messages are sent both to the console and to a logfile. 
Log messages are generated via the "logging" package.

Example:
    >>> import duallog
    >>> import logging
    >>> duallog.setup('mylogs')
    >>> logging.info('Test message')

If run, this module illustrates the usage of the duallog package.
"""


# Import required standard packages.
import datetime
import logging.handlers
import os

# Define default logfile format.
file_name_format = '{year:04d}{month:02d}{day:02d}-'\
    '{hour:02d}{minute:02d}{second:02d}.log'

# Define the default logging message formats.
file_msg_format = '%(asctime)s %(levelname)-8s: %(message)s'
console_msg_format = '%(levelname)s: %(message)s'

# Define the log rotation criteria.
max_bytes=1024**2
backup_count=100


def setup(dir='log', minLevel=logging.WARNING, rotation='size', keep=backup_count):
    """ Set up dual logging to console and to logfile.

    When this function is called, it first creates the given logging output directory. 
    It then creates a logfile and passes all log messages to come to it. 
    The name of the logfile encodes the date and time when it was created, for example "20181115-153559.log". 
    All messages with a certain minimum log level are also forwarded to the console.

    Args:
        dir: path of the directory where to store the log files. Both a
            relative or an absolute path may be specified. If a relative path is
            specified, it is interpreted relative to the working directory.
            Defaults to "log".
        minLevel: defines the minimum level of the messages that will be shown      on the console. Defaults to WARNING. 
    """

    # Create the root logger.
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Validate the given directory.
    dir = os.path.normpath(dir)

    # Create a folder for the logfiles.
    if not os.path.exists(dir):
        os.makedirs(dir)

    # Construct the name of the logfile.
    t = datetime.datetime.now()
    file_name = file_name_format.format(year=t.year, month=t.month, day=t.day,
        hour=t.hour, minute=t.minute, second=t.second)
    file_name = os.path.join(dir, file_name)

    # Set up logging to the logfile.
    if rotation == 'daily':
        file_name = "{}.log".format(dir)
        file_name = os.path.join(dir, file_name)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=file_name, when='midnight', backupCount=keep)
    elif rotation == 'hourly':
        file_name = "{}.log".format(dir)
        file_name = os.path.join(dir, file_name)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=file_name, when='H', backupCount=keep)
    else:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=file_name, maxBytes=max_bytes, backupCount=keep)

    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(file_msg_format)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Set up logging to the console.
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(minLevel)
    stream_formatter = logging.Formatter(console_msg_format)
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)


if __name__ == '__main__':
    """Illustrate the usage of the duallog package.
    """

    # Set up dual logging.
    setup('logtest')

    # Generate some log messages.
    logging.debug('Debug messages are only sent to the logfile.')
    logging.info('Info messages are not shown on the console, too.')
    logging.warning('Warnings appear both on the console and in the logfile.')
    logging.error('Errors get the same treatment.')
    logging.critical('And critical messages, of course.')

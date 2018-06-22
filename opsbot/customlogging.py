"""A custom logging commands script that can write and return logs."""

import opsbot.config as config
from datetime import datetime
import json
import os

sql_log_base = config.LOG_PATH

def info(message):
    """Logs the message at this time and writes it to the correct log."""
    message = (str(datetime.today()) + " - " + message)
    filename = datetime.today().strftime("%m-%Y.csv")
    if os.path.exists('{}{}'.format(sql_log_base, filename)):
        fd = open('{}{}'.format(sql_log_base, filename), 'a')
    else:
        fd = open('{}{}'.format(sql_log_base, filename), "w+")
    fd.write(message)
    fd.close()

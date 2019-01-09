"""A custom logging commands script that can write and return logs."""

try:
    import opsbot.config as config
except ModuleNotFoundError:
    import config
from datetime import datetime
import json
import os
import requests

sql_log_base = config.LOG_PATH


def betterprint(text):
    """Print only if there is a console to print to."""
    try:
        print(text)
    except OSError as e:
        pass


def info(message, server=None, database=None, action="other"):
    """Logs the message at this time and writes it to the correct log."""
    if not server and not database:
        return
    message = (server + " database=" + database + " user=" + message)
    message = ("time=" + str(datetime.today()) + " server=" + message)
    message = (message + " action=" + action)

    #filename = "temp.csv"

    #fd = open('{}{}'.format(sql_log_base, filename), "w+")

    #fd.write(message)
    #fd.close()

    #file = "{}{}".format(sql_log_base, filename)
    #print ("message written to {}".format(filename))

    if config.SUMOLOGIC_ENDPOINT:
        #with open(file) as f:
        r = requests.post(config.SUMOLOGIC_ENDPOINT, data=message)
        betterprint(r)

    with open("log/events.log", "a") as f:
        f.write(message)

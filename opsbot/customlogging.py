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

def info(message, server=None, database=None):
    """Logs the message at this time and writes it to the correct log."""
    if not server and not database:
        return
    message = (server + " database=" + database + " user=" + message)
    message = ("time=" + str(datetime.today()) + " server=" + message)

    #filename = "temp.csv"

    #fd = open('{}{}'.format(sql_log_base, filename), "w+")

    #fd.write(message)
    #fd.close()

    #file = "{}{}".format(sql_log_base, filename)
    #print ("message written to {}".format(filename))

    if config.SUMOLOGIC_ENDPOINT:
        #with open(file) as f:
        r = requests.post(config.SUMOLOGIC_ENDPOINT, data=message)
        print (r)

    with open("log/events.log", "a") as f:
        f.write(message)

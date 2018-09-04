"""A custom logging commands script that can write and return logs."""

import opsbot.config as config
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

    #filename = datetime.today().strftime("%m-%Y.csv")
    filename = "temp.csv"
    # if os.path.exists('{}{}'.format(sql_log_base, filename)):
    #     fd = open('{}{}'.format(sql_log_base, filename), 'a')
    # else:
    #     fd = open('{}{}'.format(sql_log_base, filename), "w+")
    fd = open('{}{}'.format(sql_log_base, filename), "w+")

    fd.write(message)
    fd.close()

    file = "{}{}".format(sql_log_base, filename)
    print ("message written to {}".format(filename))
    with open(file) as f:
        r = requests.post(config.SUMOLOGIC_ENDPOINT, data={"file": f})
        print (r)

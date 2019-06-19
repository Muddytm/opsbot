import opsbot.customlogging as logging
import json
import os
import pyodbc

from datetime import datetime
from datetime import timedelta
import opsbot.config as config

db_path = config.DATA_PATH + 'databases.json'

# to solve the issue of removing servers from list that is being iterated over
servers_to_remove = []

def betterprint(text):
    """Print only if there is a console to print to."""
    try:
        print(text)
    except OSError as e:
        pass


def execute_sql(sql, server, database=None, get_rows=False, userdata=None):
    """Execute a SQL statement."""

    global servers_to_remove

    if server == "mcgintsql01":
        user = config.AZURE_USER + "@" + server
        password = config.AZURE_PASSWORD
        server = "tcp:{}.database.windows.net".format(config.AZURE_DB)
    elif server == "SQLCLUSTER02":
        user = config.SQL_USER
        password = config.SQL_PASSWORD # TODO: replace in config
        server = config.SQL_SERVER_2 # TODO: replace
    elif server == "SQLCLUSTER01":
        user = config.SQL_USER
        password = config.SQL_PASSWORD # TODO: replace in config
        server = config.SQL_SERVER_1 # TODO: replace

    db = ''
    rows = []
    if database:
        db = 'Database=' + database + ";"
    else:
        db = ""

    #conn_string = 'DSN={};UID={};PWD={};{}'.format(dsn, user, password, db)
    conn_string = ("Driver={{ODBC Driver 17 for SQL Server}};Server={}" +
                   ",1433;{}Uid={};Pwd={};" +
                   "Encrypt=yes;TrustServerCertificate=yes;Connection " +
                   "Timeout=30;").format(server, db, user, password)
    #print (conn_string)
    #print (sql)
    count = 0
    while count < 3:
        try:
            connection = pyodbc.connect(conn_string)
            cursor = connection.execute(sql)
            connection.commit()
            connection.close()
            if get_rows:
                rows = cursor.fetchall()

            servers_to_remove.append(server)
            break
        except pyodbc.InterfaceError as e:
            betterprint("Login failed. Reason: {}".format(e))
            break
        except pyodbc.OperationalError as e:
            if count < 2:
                betterprint("Timed out...trying again. Reason: {}".format(e))
            else:
                betterprint("Timed out for the third time, I'm outta here.")
                break
        except pyodbc.ProgrammingError as e:
            betterprint("Cannot access this server: {}".format(e))
            if "user is currently logged in" in e.args[1]:
                with open("data/jobs.json") as f:
                    jobs = json.load(f)

                if "{}:{}".format(userdata["name"], server) not in jobs and "{}:{}:DONE".format(userdata["name"], server) not in jobs:
                    jobs.append("{}:{}".format(userdata["name"], server))

                    with open("data/jobs.json", "w") as f:
                        json.dump(jobs, f)

                return None, userdata
            elif "it does not exist" in e.args[1] and "drop the user" not in e.args[1]:
                #userdata["servers"].remove(server)
                servers_to_remove.append(server)

                return None, userdata
            break

        count += 1

    if rows:
        return rows, userdata
    else:
        return None, userdata


def delete_sql_user(user, server, database):
    """Delete a SQL user."""
    betterprint("Deleting {} from server {} and db {}".format(user, server, database))
    #if not sql_user_exists(user, server, database):
    #    return
    sql = "DROP USER [{}]".format(user)
    #print ("lets delete it now")
    try:
        betterprint("SQL: " + sql)
        rows, userdata = execute_sql(sql, server, database)
        betterprint("USER removal successful.")
        return True
    except Exception as e:
        print (e)
        return False


def delete_sql_login(user, server, userdata):
    """Delete a SQL login."""
    betterprint("Removing LOGIN {} from server {}".format(user, server))
    sql = "DROP LOGIN [{}]".format(user)
    try:
        betterprint("SQL: " + sql)
        rows, userdata = execute_sql(sql, server, None, False, userdata)
        betterprint("LOGIN removal successful.")
        return True, userdata
    except Exception as e:
        print (e)
        return False, userdata


for filename in os.listdir("userdata/"):
    changed = False

    with open("userdata/{}".format(filename)) as data_file:
        userdata = json.load(data_file)

    if "access" not in userdata:
        continue

    name = userdata["name"]

    for i in reversed(range(len(userdata["access"]))):
        db = userdata["access"][i]["db"]
        server = userdata["access"][i]["server"]
        exp = userdata["access"][i]["expiration"]
        delta = timedelta(hours=config.HOURS_TO_GRANT_ACCESS)
        expired = datetime.now() # - delta
        user_expires = datetime.strptime(exp, "%Y-%m-%dT%H:%M:%S.%f")
        if user_expires < expired:
            data = {"db": db, "server": server}
            if data in userdata["notifications"]["deleted"]:
                success = delete_sql_user(name, server, db)
                if success:
                    logging.info("{} reason=[USER REMOVED SUCCESSFULLY]\n".format(name), server, db, "removeuser")
                    del userdata["access"][i]
                    if data in userdata["notifications"]["deleted"]:
                        userdata["notifications"]["deleted"].remove(data)
                    if data in userdata["notifications"]["tenmins"]:
                        userdata["notifications"]["tenmins"].remove(data)
                    if data in userdata["notifications"]["hour"]:
                        userdata["notifications"]["hour"].remove(data)
                    changed = True
                else:
                    logging.info("{} reason=[USER REMOVAL FAILED]\n".format(name), server, db, "removeuserfailure")

    # If list is empty, we delete logins
    if (len(userdata["access"]) == 0 and changed) or (len(userdata["access"]) == 0 and "servers" in userdata and len(userdata["servers"]) > 0):
        with open(db_path) as data_file:
            databases = json.load(data_file)
        for server in databases:
            if server in userdata["servers"]:
                success, userdata = delete_sql_login(name, server, userdata)
                if success:
                    logging.info("{} reason=[LOGIN REMOVED SUCCESSFULLY]\n".format(name), server, "[None]", "removelogin")
                    changed = True
                else:
                    changed = True
                    #logging.info("{} reason=[LOGIN REMOVAL FAILED]\n".format(name), server, "[None]", "removeloginfailure")

    if changed:
        for server in servers_to_remove:
            if server in userdata["servers"]:
                userdata["servers"].remove(server)

        with open("userdata/{}".format(filename), 'w') as outfile:
            json.dump(userdata, outfile)

        if not userdata["servers"]:
            with open("data/jobs.json") as f:
                jobs = json.load(f)

            new_jobs = []
            for job in jobs:
                if userdata["name"] not in job:
                    new_jobs.append(job)

            with open("data/jobs.json", "w") as f:
                json.dump(new_jobs, f)

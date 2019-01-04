try:
    import testscripts.config as config
except ModuleNotFoundError:
    import config
import pyodbc

#sql = "SELECT object_name ,counter_name, cntr_value\nFROM sys.dm_os_performance_counters\nWHERE counter_name = 'Target Server Memory (KB)'"
sql = "DROP USER IF EXISTS [{}]".format(config.TEST_USER)

conn_string = "DRIVER={};SERVER={};DATABASE={};UID={};PWD={}".format("{ODBC Driver 17 for SQL Server}", config.SQL_SERVER, config.TEST_DB, config.SQL_USER, config.SQL_PASSWORD)

try:
    connection = pyodbc.connect(conn_string)
    cursor = connection.execute(sql)
    rows = cursor.fetchall()
    connection.commit()
    connection.close()

    print (rows)
except pyodbc.ProgrammingError as e:
    print ("Could not log in to {}: {}".format("SQLCLUSTER02", e))

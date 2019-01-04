try:
    import testscripts.config as config
except ModuleNotFoundError:
    import config
import pyodbc

#sql = "SELECT object_name ,counter_name, cntr_value\nFROM sys.dm_os_performance_counters\nWHERE counter_name = 'Target Server Memory (KB)'"
sql = "select name FROM sys.databases;"

conn_string = "DRIVER={};SERVER={};UID={};PWD={}".format("{ODBC Driver 17 for SQL Server}", config.SQL_SERVER, config.TEST_USER, config.TEST_PASSWORD)

try:
    connection = pyodbc.connect(conn_string)
    cursor = connection.execute(sql)
    rows = cursor.fetchall()
    connection.commit()
    connection.close()

    #print (rows)
    for row in rows:
        print (row[0])
except pyodbc.ProgrammingError as e:
    print ("Could not log in to {}: {}".format("SQLCLUSTER02", e))

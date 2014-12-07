#!/usr/bin/python
# watch out for cr in line above
import sys
import json
import time
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import sqlite3
from houseutils import getHouseValues, lprint

def recordInLog():
	lprint(sys.argv[0]," Running")

#-------------------------------------------------  
# get the values out of the houserc file
hv = getHouseValues()

#-------------------------------------------------
# the database where I'm storing stuff
DATABASE= hv["database"]
buff = ''
#-------------------------------------------------
logging.basicConfig()
#------------------If you want to schedule something to happen -----
scheditem = BackgroundScheduler()
scheditem.start()
# someday this will set the rainfall amount back to zero at midnight
#scheditem.add_job(resetRain, 'cron', hour=24, minute=0)
scheditem.add_job(recordInLog, 'interval', minutes=30)

recordInLog()
while True:
    try:
        buff += sys.stdin.read(1) #This is a blocking read
        if buff.endswith('\n'):
            try:
                data = json.loads(buff[:-1])
                # print "On", time.strftime("%A, %B, %d at %H:%M:%S",time.localtime(float(data["windSpeed"]["t"]))),
                # print "the wind was blowing from the", data["windDirection"]["WD"],
                # print "at\n", data["windSpeed"]["WS"], "mph,",
                # print "and it is", data["temperature"]["T"], "degrees F Outside.",
                # print "The humidity is", data["humidity"]["H"], "percent",
                # print "and \nthe rain counter is", data["rainCounter"]["RC"],
                # print
                # sys.stdout.flush()
            except ValueError:
                lprint("Input wasn't JSON");
                lprint(data);
            # For now just store the whole string in the database.
            dbconn = sqlite3.connect(DATABASE)
            c = dbconn.cursor()
            # update database stuff
            try:
                sqlString = json.dumps(buff[:-1])
                #print sqlString
                c.execute("update weather set 'json' = ?;",
                    (sqlString,))
                dbconn.commit()
            except sqlite3.OperationalError:
                lprint("Database is locked, record skipped")
            dbconn.close()
            buff = ''


    except KeyboardInterrupt:
            sys.stdout.flush()
            sys.exit()
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
DATABASE= hv["database"]

buff = ''
data = ""
char = ""
#-------------------------------------------------
logging.basicConfig()
#------------------If you want to schedule something to happen -----
scheditem = BackgroundScheduler()
scheditem.start()
# someday this will update parameters at midnight
#scheditem.add_job(midnightReset, 'cron', hour=24, minute=0)
scheditem.add_job(recordInLog, 'interval', minutes=30)

recordInLog()
while True:
    try:
        char = sys.stdin.read(1) #This is a blocking read
        # you have no idea how hard it was to discover this.
        # and end of file on a piped in input is a length of 
        # zero.  There's about a thousand wrong answers out there
        # and I never did find the right one.  Thank goodness
        # for good old trial and error.
        if len(char) == 0:
            break # the pipe is gone, just exit the process
        else:
            buff += char;
        if buff.endswith('\n'):
            try:
                data = json.loads(buff[:-1])
                # print "On", time.strftime("%A, %B, %d at %H:%M:%S",time.localtime(float(data["windSpeed"]["t"]))),
                # print "the wind was blowing from the", data["windDirection"]["WD"],
                # print "at\n", data["windSpeed"]["WS"], "mph,",
                # print "and it is", data["temperature"]["T"], "degrees F Outside.",
                # print "The humidity is", data["humidity"]["H"], "percent",
                # print "and \nthe rain counter is", data["rainCounter"]["RC"],
                # print "the barometer is at", data["barometer"]["BP"],
                # print
                # sys.stdout.flush()
            except ValueError:
                lprint("Input wasn't JSON");
                lprint(buff);
                buff = ''
                continue
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
        lprint("Cntl-C from user");
        break;
        
scheditem.shutdown(wait=False)
sys.stdout.flush()
sys.exit("Done")
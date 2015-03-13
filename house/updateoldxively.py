#!/usr/bin/python
import xively
import sys
import os
import signal
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import logging
import time
import sqlite3
from houseutils import getHouseValues, lprint

def specialTempSensor(c, when):
    # get the time out of the database
    timeString = c.execute(
        "select utime from TempSensor where name = 'Temp1'").fetchone()[0]
    # convert the string into seconds
    # I don't keep the current year in the database (dumb mistake)
    # so I have to seriously fudge things
    writeable = list(time.strptime(timeString,"%A, %B, %d at %H:%M:%S"))
    writeable[0] = time.localtime()[0]
    then = time.mktime(time.struct_time(tuple(writeable)))
    # do the same with the local time; this one is easier
    now = time.mktime(time.localtime())
    # I can finally make the comparison
    if ( now - then > 5*60):
        return 0
    return c.execute(
            "select pvolt from TempSensor where name = 'Temp1'").fetchone()[0]
    


# This is where the update to Xively happens
def updateXively():
    lprint ("Updating Xively Legacy ")
    sys.stdout.flush()
    # Currently I have to use UTC for the time,
    # there's a bug somewhere in the library or 
    # Xively.  It doesn't matter though because
    # it's easy to convert
    now = datetime.datetime.utcnow()
    # open the database
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    # Yes, there are better ways to do the stuff below,
    # but I wanted to use a single statement to get it 
    # from the data base and update the fields going to 
    # Xively.  It turns out that is is a rather odd
    # looking statement, but it works.
    # However, I noticed that fetchone() returns a tuple
    # with only one value in it (value,) which means
    # I have to get at it with a [0].  
    tmp = c.execute("select motor from pool").fetchone()[0];
    if (tmp == 'High'): # a little special handling for the pool motor
        motor = 2
    elif (tmp == 'Low'):
        motor = 1
    else:
        motor = 0
    feed.datastreams = [
       xively.Datastream(id='7', 
            current_value = c.execute(
                "select temperature from Barometer")
                .fetchone()[0], 
            at=now),
        xively.Datastream(id='0', 
            current_value = c.execute(
                "select rpower from power")
                .fetchone()[0],  
            at=now),
        xively.Datastream(id='4', 
            current_value = c.execute(
                "select voltage from power")
                .fetchone()[0],  
            at=now),
        xively.Datastream(id='1', 
            current_value = c.execute(
                "select apower from power")
                .fetchone()[0],  
            at=now),
        xively.Datastream(id='3', 
            current_value = c.execute(
                "select current from power")
                .fetchone()[0],  
            at=now),
        xively.Datastream(id='5', 
            current_value = c.execute(
                "select frequency from power")
                .fetchone()[0],  
            at=now),
        xively.Datastream(id='2', 
            current_value = c.execute(
                "select pfactor from power")
                .fetchone()[0],  
            at=now),
        xively.Datastream(id='6',
            current_value = c.execute(
                "select avg(\"temp-reading\") from thermostats")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='8',
            current_value = motor,
            at=now),
        xively.Datastream(id='9',
            current_value = c.execute(
                "select ptemp from pool")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='10',
            current_value = c.execute(
                "select watts from smartswitch where name = 'refrigerator'")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='11',
            current_value = c.execute(
                "select watts from smartswitch where name = 'freezer'")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='12',
            current_value = c.execute(
                "select watts from smartswitch where name = 'garagefreezer'")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='13',
            current_value = c.execute(
                "select watts from smartswitch where name = 'monitor'")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='14',
            current_value = c.execute(
                "select pressure from barometer")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='15',
            current_value = c.execute(
                "select temp from TempSensor where name = 'Temp1'")
            .fetchone()[0],
            at=now),
        xively.Datastream(id='16',
            current_value = specialTempSensor(c, now),
            at=now)
        ]
    try:
        # update the time in the database
        feed.update()  # and update Xively with the latest
        c.execute("update oldxively set utime=?;",(time.strftime("%A, %B, %d at %H:%M:%S"),))
        dbconn.commit()
        dbconn.close() # close the data base
    except:
        lprint ("error: " + str(sys.exc_info()[0]))

if __name__ == "__main__":
    lprint ("started")
    logging.basicConfig()
    # get the values I need from the rc file
    # The Xively feed id and API key that is needed
    hv = getHouseValues()
    FEED_ID = hv["oldxively"]["feed"]
    API_KEY = hv["oldxively"]["key"]
    # the database where I'm storing stuff
    DATABASE= hv["database"]

    #------------------Stuff I schedule to happen -----
    scheditem = BackgroundScheduler()
    scheditem.start()
    # every minute update the data store on Xively
    # may have to use max_instances to allow for web problems
    scheditem.add_job(updateXively, 'interval', seconds=60, max_instances=2)
    #--------------------Xively interface----------------
    # Initialize Xively api client
    api = xively.XivelyAPIClient(API_KEY)
    # and get my Xively feed
    feed = api.feeds.get(FEED_ID)

    updateXively()
    while True:
        time.sleep(20) #This doesn't matter much since it is schedule driven

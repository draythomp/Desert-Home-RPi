#!/usr/bin/python
import xively
import sys
import os
import signal
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import logging
import time
import MySQLdb as mdb
from houseutils import getHouseValues, lprint, dbTimeStamp

def specialTempSensor(hc):
    # get the time out of the database
    timeString = hc.execute(
        "select utime from tempsensor where name = 'Temp1'")
    timeString = hc.fetchone()[0]
    # convert the string into seconds
    then = long(timeString)
    # get the local time
    now = long(dbTimeStamp())
    # I can finally make the comparison
    if ( now - then > 5*60):
        return 0
    hc.execute(
            "select pvolt from tempsensor where name = 'Temp1'")
    return hc.fetchone()[0]
    
def getIt(c, query):
    try:
        c.execute(query)
        result = c.fetchone()[0]
        #print "gotback", result
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    return result

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
    try:
        wdbconn = mdb.connect(host=wdbHost, user=wdbUser, passwd=wdbPassword, db=wdbName)
        wc = wdbconn.cursor()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        
    # Yes, there are better ways to do the stuff below,
    # but I wanted to use a single statement to get it 
    # from the data base and update the fields going to 
    # Xively.  It turns out that is is a rather odd
    # looking statement, but it works.
    # However, I noticed that fetchone() returns a tuple
    # with only one value in it (value,) which means
    # I have to get at it with a [0].  
    hc.execute("select motor from pool")
    tmp = hc.fetchone()[0]
    if (tmp == 'High'): # a little special handling for the pool motor
        motor = 2
    elif (tmp == 'Low'):
        motor = 1
    else:
        motor = 0
    feed.datastreams = [
       xively.Datastream(id='7', 
            current_value = getIt(wc,
            "select reading from ftemperature order by rdate desc limit 1"), 
            at=now),
        xively.Datastream(id='0', 
            current_value = getIt(hc,
                "select rpower from power order by utime desc limit 1"),  
            at=now),
        xively.Datastream(id='4', 
            current_value = getIt(hc,
                "select voltage from power"),
            at=now),
        xively.Datastream(id='1', 
            current_value = getIt(hc,
                "select apower from power"),
            at=now),
        xively.Datastream(id='3', 
            current_value = getIt(hc,
                "select current from power"),
            at=now),
        xively.Datastream(id='5', 
            current_value = getIt(hc,
                "select frequency from power"),
            at=now),
        xively.Datastream(id='2', 
            current_value = getIt(hc,
                "select pfactor from power"),
            at=now),
        xively.Datastream(id='6',
            current_value = getIt(hc,
                "select avg(`temp-reading`) from thermostats"),
            at=now),
        xively.Datastream(id='8',
            current_value = motor,
            at=now),
        xively.Datastream(id='9',
            current_value = getIt(hc,
                "select ptemp from pool"),
            at=now),
        xively.Datastream(id='10',
            current_value = getIt(hc,
                "select watts from smartswitch where name = 'refrigerator'"),
            at=now),
        xively.Datastream(id='11',
            current_value = getIt(hc,
                "select watts from smartswitch where name = 'freezer'"), 
            at=now),
        xively.Datastream(id='12',
            current_value = getIt(hc,
                "select watts from smartswitch where name = 'garagefreezer'"), 
           at=now),
        xively.Datastream(id='13',
            current_value = getIt(hc,
                "select watts from smartswitch where name = 'monitor'"), 
            at=now),
        xively.Datastream(id='14',
            current_value = getIt(wc,"select reading from barometer order by rdate desc limit 1"), 
            at=now),
        xively.Datastream(id='15',
            current_value = getIt(hc,
                "select temp from tempsensor where name = 'Temp1'"),
            at=now),
        xively.Datastream(id='16',
            current_value = specialTempSensor(hc),
            at=now)
        ]
    try:
        # update the time in the database
        feed.update()  # and update Xively with the latest
        hc.execute("update oldxively set utime=%s;",(dbTimeStamp(),))
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        dbconn.close() # close the data base
    except:
        lprint ("error: " + str(sys.exc_info()[0]))
    
    wdbconn.close()
    hdbconn.close()


if __name__ == "__main__":
    lprint ("started")
    logging.basicConfig()
    # get the values I need from the rc file
    # The Xively feed id and API key that is needed
    hv = getHouseValues()
    FEED_ID = hv["oldxively"]["feed"]
    API_KEY = hv["oldxively"]["key"]
    
    # the old database where I'm storing stuff. Soon to be removed
    DATABASE= hv["database"]
    
    # the database where I'm storing weather stuff
    wdbName = hv["weatherDatabase"]
    wdbHost = hv["weatherHost"]
    wdbPassword = hv["weatherPassword"]
    wdbUser = hv["weatherUser"]
    
    # the database where I'm storing house stuff
    hdbName = hv["houseDatabase"]
    hdbHost = hv["houseHost"]
    hdbPassword = hv["housePassword"]
    hdbUser = hv["houseUser"]
    
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

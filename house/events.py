#! /usr/bin/python
# This is the module that holds timers for various actions
# that I want to happen periodically around the house
#
from apscheduler.schedulers.background import BackgroundScheduler
import subprocess
import logging
from datetime import datetime, timedelta
import time
import urllib2
import BaseHTTPServer
import sqlite3
import sys
import sysv_ipc
from houseutils import lprint, getHouseValues

#--------This is for the HTML interface 
def openSite(Url):
    lprint (Url)
    webHandle = None
    try:
        webHandle = urllib2.urlopen(Url, timeout=5) #if it doesn't answer in 5 seconds, it won't
    except urllib2.HTTPError, e:
        errorDesc = BaseHTTPServer.BaseHTTPRequestHandler.responses[e.code][0]
        print "Error: cannot retrieve URL: " + str(e.code) + ": " + errorDesc
    except urllib2.URLError, e:
        print "Error: cannot retrieve URL: " + e.reason[1]
    except:  #I kept getting strange errors when I was first testing it
        e = sys.exc_info()[0]
        print ("Odd Error: %s" % e )
        raise
    return webHandle

def talkHTML(ip, command):
    website = openSite("HTTP://" + ip + '/' + urllib2.quote(command, safe="%/:=&?~#+!$,;'@()*[]"))
    # now (maybe) read the status that came back from it
    if website is not None:
        websiteHtml = website.read()
        return  websiteHtml

#-------These are the jobs that get scheduled----------------
def bedroomLightOn():
    talkHTML(irisControl,"command?whichone=monitor&what=on");

def bedroomLightOff():
    talkHTML(irisControl,"command?whichone=monitor&what=off");

def outsideLightsOn():
    talkHTML(wemoController,"pCommand?command=OutsideLightsOn");
    lprint ("Turn on Outside Lights")
    
def outsideLightsOff():
    talkHTML(wemoController,"pCommand?command=OutsideLightsOff");
    lprint ("Turn off Outside Lights")

def acidPumpOn():
    talkHTML(houseMonitor,"pCommand?command=AcidPump pumpOn");
    lprint ("Acid Pump on")

def poolMotorOff(message=None):
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    tmp = c.execute("select motor from pool").fetchone()[0];
    if message is not None:
        lprint(message)
    lprint ("Pool pump is currently: ", tmp)
    if (tmp == 'High' or tmp == 'Low'):
        talkHTML(houseMonitor,"pCommand?command=Pool pumpoff");
        #sendCommand("Pool pumpoff")
        lprint ("Pool Pump Off")
        #set a timer to come back here in a minute to be sure it goes off
        scheditem.add_job(poolMotorOff, 'date', 
            run_date=datetime.now() + timedelta(minutes=1), 
            args=["Double Checking"])
    dbconn.close() # close the data base
    
def poolMotorOnHigh(message=None):
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    tmp = c.execute("select motor from pool").fetchone()[0];
    if message is not None:
        lprint(message)
    lprint ("Pool pump is currently: ", tmp)
    if (tmp == 'Off' or tmp == 'Low'):
        talkHTML(houseMonitor,"pCommand?command=Pool pumphigh");
        lprint ("Pool Pump On High")
        scheditem.add_job(poolMotorOnHigh, 'date', 
            run_date=datetime.now() + timedelta(minutes=1), 
            args=["Double Checking"])
    dbconn.close() # close the data base

def poolMotorOnLow(message=None):
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    tmp = c.execute("select motor from pool").fetchone()[0];
    if message is not None:
        lprint(message)
    lprint ("Pool pump is currently: ", tmp)
    if (tmp == 'Off' or tmp == 'High'):
        talkHTML(houseMonitor,"pCommand?command=Pool pumplow");
        lprint ("Pool Pump On Low")
        scheditem.add_job(poolMotorOnLow, 'date', 
            run_date=datetime.now() + timedelta(minutes=1), 
            args=["Double Checking"])
    dbconn.close() # close the data base
    
def fansRecirc():
    talkHTML(houseMonitor,"pCommand?command=preset recirc");
    lprint("A/C fans to recirc")

def fansAuto():
    talkHTML(houseMonitor,"pCommand?command=preset auto");
    lprint ("A/C fans to auto")

def sendMail(subject, body):
    mailPassword = hv["mailpassword"]

    try:
        print subprocess.check_output(["sendEmail", 
            "-f", hv["emailaddr"],
            '-t', hv["emailaddr"],
            '-u', subject,
            '-m', body,
            '-s', 'smtp.gmail.com:587',
            '-o',
            'tls=yes',
            '-xu', hv["emailuser"],
            '-xp', hv["mailpassword"]], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError, e:
        print e.output
        print e.cmd

def sendStatusMail():
    sendMail("Normal Status", "I'm alive");
    
def testJob():
    lprint("sending preset test command")
    talkHTML(houseMonitor,"pCommand?command=preset test");

# Attach to the message queue where commands can be sent to
# the house monitor.

logging.basicConfig()
# Grab the values out of the rc file
hv = getHouseValues()
DATABASE = hv["database"]
lprint("Using database ", DATABASE);
wemoController = hv["wemocontrol"]["ipAddress"] + ":" + \
                    str(hv["wemocontrol"]["port"])
lprint("Wemo Controller is:", wemoController);
houseMonitor = hv["monitorhouse"]["ipAddress"] + ":" + \
                    str(hv["monitorhouse"]["port"])
lprint("House Monitor is:", houseMonitor);
irisControl = hv["iriscontrol"]["ipAddress"] + ":" + \
                    str(hv["iriscontrol"]["port"])
lprint("Iris Control is:", irisControl);

#------------------Stuff I schedule to happen -----
scheditem = BackgroundScheduler()

# Right now I don't have much that I want to have scheduled to 
# happen.  There are some things that come up from time to
# time that get added and taken out later.  This makes it
# easy to do without killing any of the other processes.

# Turn the front outside lights on every evening at 1900 (7PM)
scheditem.add_job(outsideLightsOn, 'cron', hour=19, minute=0)

# Turn the front outside lights off every evening at 2200 (10PM)
scheditem.add_job(outsideLightsOff, 'cron', hour=22, minute=0)

# Every weekday (M-F) set the A/C fans to auto instead of recirculate
scheditem.add_job(fansAuto, 'cron', day_of_week='mon-fri', hour=11, minute=55)

# Every weekday (M-F) put the fans to recirculate for the evening
scheditem.add_job(fansRecirc, 'cron', day_of_week='mon-fri', hour=19, minute=1)

# Specifically turn the pool motor off in case I forget
scheditem.add_job(poolMotorOff, 'cron', hour=22, minute=0,args=["Pool Off for the night."])

# Specifically turn the pool motor on (high) to get some filter time
scheditem.add_job(poolMotorOnHigh, 'cron', hour=19, minute=2,args=["Start pool motor (high)"])

# Specifically turn the pool motor on (low) to get some solar time
# scheditem.add_job(poolMotorOnLow, 'cron', hour=7, minute=0,args=["Start pool motor (high)"])

# Run the acid pump in the morning, every day
# Acid pump shuts itself off automatically.
scheditem.add_job(acidPumpOn, 'cron', hour=8, minute=0)

# Turn the lights on by my bed at 9PM every day
scheditem.add_job(bedroomLightOn, 'cron', hour=21, minute=0)
# and then back off if I'm not there to do it
scheditem.add_job(bedroomLightOff, 'cron', hour=2, minute=0)

# This one is only to test the interaction between processes
#scheditem.add_job(testJob, 'interval', seconds=15)

#This one sends status mail to me periodically
scheditem.add_job(sendStatusMail, 'cron', hour=6, minute=30)
#Finally, start the scheduler to handle things
scheditem.start()

#------------------------------------------------------------
# Now do nothing while the scheduler takes care of things for me
lprint("started")

while (1):
    try:
        time.sleep(0.1)
        sys.stdout.flush()
    except KeyboardInterrupt:
        scheditem.shutdown(wait=False) # shut down the apscheduler
        sys.exit("Told to shut down");

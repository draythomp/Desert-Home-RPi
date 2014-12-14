#! /usr/bin/python
from houseutils import getHouseValues, lprint
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import datetime
from datetime import timedelta
import time
import sqlite3
import sys
import sysv_ipc
import cherrypy

def sendMail(subject, body):
    global mailTime
    
    now = datetime.datetime.now()
    if ( now < (mailTime + timedelta(hours=1)) ):
        return
    try:
        lprint (subprocess.check_output(["sendEmail", 
            "-f", hv["emailaddr"],
            '-t', hv["emailaddr"],
            '-u', subject,
            '-m', body,
            '-s', 'smtp.gmail.com:587',
            '-o',
            'tls=yes',
            '-xu', hv["emailuser"],
            '-xp', hv["mailpassword"]], stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError, e:
        lprint (e.output)
        lprint (e.cmd)
    mailTime = datetime.datetime.now()

def processExists(procs):
    notFound = []
    
    def checkList(psList, proc):
        for line in psList.split("\n"):
            if line != "" and line != None:
                fields = line.split()
                pid = fields[0]
                pname = fields[3]
            if(pname == proc[0:15]): # ps will truncate the name
                return True
        return False

    ps = subprocess.Popen("ps -A", shell=True, stdout=subprocess.PIPE)
    ps_pid = ps.pid
    output = ps.stdout.read()
    ps.stdout.close()
    ps.wait()

    for proc in procs:
        if (not checkList(output,proc)):
            notFound.append(proc)
    return notFound
    
def checkUpdateTimes(items):
    notReporting = []
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    collected = {}
    for item in items:
        if (item == 'thermostats'):
            c.execute("select utime from thermostats where location = 'North';")
            updateTime = c.fetchone()
            collected.update({"Nthermo" : updateTime})
            c.execute("select utime from thermostats where location = 'South';")
            updateTime = c.fetchone()
            collected.update({"Sthermo" : updateTime})
        if (item == 'smartswitch'):
            c.execute("select utime from smartswitch where name = 'refrigerator';")
            updateTime = c.fetchone()
            collected.update({"Refrigerator" : updateTime})
            c.execute("select utime from smartswitch where name = 'freezer';")
            updateTime = c.fetchone()
            collected.update({"Freezer" : updateTime})
            c.execute("select utime from smartswitch where name = 'garagefreezer';")
            updateTime = c.fetchone()
            collected.update({"GFreezer" : updateTime})
        if (item == 'lights'):
            c.execute("select utime from lights where name = 'outsidegarage';")
            updateTime = c.fetchone()
            collected.update({"outsidegarage" : updateTime})
            c.execute("select utime from lights where name = 'frontporch';")
            updateTime = c.fetchone()
            collected.update({"frontporch" : updateTime})
            c.execute("select utime from lights where name = 'cactusspot';")
            updateTime = c.fetchone()
            collected.update({"cactusspot" : updateTime})
        else:
            c.execute("select utime from '%s';"% item)
            updateTime = c.fetchone()
            collected.update({item : updateTime})
    dbconn.close()
    now = datetime.datetime.now()
    for key, value in collected.items():
        lastTime = datetime.datetime.strptime(value[0],
            "%A, %B, %d at %H:%M:%S").replace(year=now.year)
        if ( now > (lastTime + timedelta(minutes=5)) ):
            notReporting.append(key)
    return notReporting

def checkOtherThings():
    problemThings = []
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    #Check the Acid Pump level 
    c.execute("select level from acidpump;")
    level = c.fetchone()
    if (level[0] != 'OK'):
        problemThings.append("Acid Pump Low");
    dbconn.close()
    return problemThings
    
processList = ["updatexively.py", "updateoldxively.py",
                "monitorhouse.py", "updategrovestream.py",
                "updatets.py", "wemocontrol.py",
                "events.py", "watchappliance.py","updateemon.py"]
recordList = ["acidpump","emoncms", "garage", "grovestream", 
                "oldxively", "pool", "power", "septic", "thermostats", 
                "thingspeak", "xbeetemp", "xively", "smartswitch", "lights"]

def monitorTheMonitor():
    #Check to see if all the processes are running
    deadOnes = processExists(processList)
    lateOnes = checkUpdateTimes(recordList)
    if (len(deadOnes) != 0 or len(lateOnes) != 0):
        badThings = "Problems with %s %s"%(str(deadOnes), str(lateOnes))
        lprint ("Problem with: ", badThings)
        sendMail("Problem Found", badThings)
    otherThings = checkOtherThings()
    if (len(otherThings) != 0):
        somethingBad = "Go check %s"%(str(otherThings))
        lprint ("Problem with:", somethingBad)
        sendMail("Problem Found", somethingBad)

def fixProcess(process):
    try:
        tmp = subprocess.check_output(["status", process],stderr=subprocess.STDOUT)
        if "running" in tmp:
            lprint (process, "is running")
            lprint (subprocess.check_output(["sudo", "restart", process], 
                stderr=subprocess.STDOUT))
        else:
            lprint (process, "not running")
            lprint (subprocess.check_output(["sudo", "start", process], 
                stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError, e:
        lprint (e.output)
        lprint (e.cmd)


def handleCommand(command):
    # Commands come in as something like 'reset all'
    #print command
    c = str(command[0]).split(' ') 
    #print repr(c)
    todo = c[0]
    what = c[1].strip(' ')
    # now I have a list like ['todo', 'what']
    lprint ("command is:",todo,what)
    if (todo == 'reset'):
        lprint ("This is where the reset happens")
        if (what == 'all'):
            lprint ("Doing a master reset")
            processes = ["monitorhouse", "houseevents", "wemocontrol",
                    "updateemon", "updategrovestream", "updatets", "updatexively",
                    "updateoldxively", "watchappliance"]
            for process in processes:
                fixProcess(process)
        else:
            lprint ("Unimplemented process")
    else:
        lprint ("Unimplemented Command")

# First the process interface, it consists of a status report and
# a command receiver.
class healthcheckSC(object):
    
    @cherrypy.expose
    def pCommand(self, command):
        handleCommand((command,0));

    @cherrypy.expose
    def index(self):
        status = "<strong>Health Check</strong><br /><br />"
        status += "is actually alive<br />"
        status += "<br />"
        return status
        
def gracefulEnd():
    lprint("****************************got to gracefulEnd")
    scheditem.shutdown(wait=False)

if __name__ == '__main__':
    hv = getHouseValues()
    # the database where I'm storing stuff
    DATABASE= hv["database"]
    # Get the ip address and port number you want to use
    # from the houserc file
    ipAddress=hv["healthcheck"]["ipAddress"]
    port = hv["healthcheck"]["port"]

    mailTime = 0;

    lprint ("started")

    logging.basicConfig()
    mailTime = datetime.datetime.now().replace(year=1900) #init mail limit timer
    monitorTheMonitor() #so I don't have to wait when debugging

    #------------------Stuff I schedule to happen -----
    scheditem = BackgroundScheduler()
    # every 10 minutes check the processes and device updates
    scheditem.add_job(monitorTheMonitor, 'interval', minutes=10)
    scheditem.start()
    
    # Now configure the cherrypy server using the values
    cherrypy.config.update({'server.socket_host' : ipAddress.encode('ascii','ignore'),
                            'server.socket_port': port,
                            'engine.autoreload.on': False,
                            })
    # This subscribe will catch the exit and shutdown the apscheduler 
    # for a nice exit.
    cherrypy.engine.subscribe("exit", gracefulEnd);

    try:
        lprint ("Hanging on the wait for HTTP messages")
        # Now just hang on the HTTP server looking for something to 
        # come in.  The cherrypy dispatcher will update the things that
        # are subscribed which will handle other things
        cherrypy.quickstart(healthcheckSC())
    except KeyboardInterrupt:
        scheditem.shutdown(wait=False)
        sys.exit("Told to shut down");

#! /usr/bin/python
from houseutils import getHouseValues, lprint
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import datetime
from datetime import timedelta
import time
import MySQLdb as mdb
import sys
import cherrypy
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

def sendMail(subject, body):
    global mailTime
    
    now = datetime.datetime.now()
    if ( now < (mailTime + timedelta(hours=1)) ):
        return
    try:
        fromaddr = hv["emailaddr"]
        toaddr = hv["emailaddr"]
        msg = MIMEMultipart()
        msg['From'] = fromaddr
        msg['To'] = toaddr
        msg['Subject'] = subject
         
        body = body
        msg.attach(MIMEText(body, 'plain'))
         
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(fromaddr, hv["mailpassword"])
        text = msg.as_string()
        server.sendmail(fromaddr, toaddr, text)
        server.quit()    
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
    
def fixTime(incoming):
    timeThing = time.strftime("%A, %B, %d, at %H:%M:%S", 
        time.localtime(int(incoming[0])))
    return (timeThing,)

def checkUpdateTimes(items):
    notReporting = []
    try:
        mdbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, db=dbName)
        mc = mdbconn.cursor()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    collected = {}
    for item in items:
        if (item == 'thermostats'):
            try:
                mc.execute("select utime from thermostats where location = 'North';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"Nthermo" : updateTime})
                mc.execute("select utime from thermostats where location = 'South';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"Sthermo" : updateTime})
            except mdb.Error, e:
                lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        elif (item == 'smartswitch'):
            try:
                mc.execute("select utime from smartswitch where name = 'refrigerator';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"Refrigerator" : updateTime})
                mc.execute("select utime from smartswitch where name = 'freezer';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"Freezer" : updateTime})
                mc.execute("select utime from smartswitch where name = 'garagefreezer';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"GFreezer" : updateTime})
            except mdb.Error, e:
                lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        elif (item == 'lights'):
            try:
                mc.execute("select utime from wemo where name = 'outsidegarage';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"outsidegarage" : updateTime})
                mc.execute("select utime from wemo where name = 'frontporch';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"frontporch" : updateTime})
                mc.execute("select utime from wemo where name = 'cactusspot';")
                updateTime = fixTime(mc.fetchone())
                collected.update({"cactusspot" : updateTime})
            except mdb.Error, e:
                 lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        elif (item == 'power'):
            try:
                mc.execute("select utime from power order by utime desc limit 1;")
                updateTime = fixTime(mc.fetchone())
                collected.update({"power" : updateTime})
            except mdb.Error, e:
                 lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        else:
            try:
                mc.execute("select utime from {0};".format(item))
                updateTime = fixTime(mc.fetchone())
                collected.update({item : updateTime})
            except mdb.Error, e:
                 lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    mdbconn.close()
    now = datetime.datetime.now()
    for key, value in collected.items():
        print key, value
        lastTime = datetime.datetime.strptime(value[0],
            "%A, %B, %d, at %H:%M:%S").replace(year=now.year)
        if ( now > (lastTime + timedelta(minutes=5)) ):
            notReporting.append(key)
    return notReporting

def checkOtherThings():
    problemThings = []
    # I used to have special devices in here and may have
    # to use it again. 
    return problemThings
    
processList = ["monitorhouse.py", "wemocontrol.py", "iriscontrol.py",
                "events.py", "updateoldxively.py", "mqttlogger.py", "savehouse.py"]
recordList = ["garage", "pool", "power", "septic", "thermostats", 
                "smartswitch", "lights", "oldxively"]

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
                "updateoldxively", "watchappliance", "iriscontrol"]
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
    
    dbName = hv["houseDatabase"]
    dbHost = hv["houseHost"]
    dbPassword = hv["housePassword"]
    dbUser = hv["houseUser"]
    
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

#! /usr/bin/python
'''
This is the House Monitor Module

It doesn't really do all the monitoring, it does capture data 
from the XBee network of devices I have (not ZigBee, that's a 
different module) and the two HTML thermostats I have and save
it to my database.

It has an extremely simple HTML interface that listens for commands, 
decodes them and passes them on to the devices for action

For the XBee network, I allow the library code to run asynchronously
and put the messages on a queue to be handled by the main thread nin 
turn.  This way, none are missed, and bursts of messages can be tamed 
a bit.

It also allows the main code to do other things during the dead periods

'''
from xbee import ZigBee 
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import datetime
import time
import serial
import signal
import Queue
import sqlite3
import sys
import urllib2
import BaseHTTPServer
import shlex
import cherrypy

from houseutils import getHouseValues, lprint

# Global items that I want to keep track of
CurrentPower = 0
DayMaxPower = 0
DayMinPower = 50000
CurrentOutTemp = 0
DayOutMaxTemp = -50
DayOutMinTemp = 200

#-------------------------------------------------
def openSite(Url):
    #print Url
    try:
        webHandle = urllib2.urlopen(Url, timeout=5) #if it doesn't answer in 5 seconds, it won't
    except urllib2.HTTPError, e:
        errorDesc = BaseHTTPServer.BaseHTTPRequestHandler.responses[e.code][0]
        print "Error: cannot retrieve URL: " + str(e.code) + ": " + errorDesc
        raise
    except urllib2.URLError, e:
        print "Error: cannot retrieve URL: " + e.reason[1]
        raise
    except urllib2.HTTPError as e:
        print e.code
        print e.read()
        raise
    except:  #I kept getting strange errors when I was first testing it
        e = sys.exc_info()[0]
        print ("Odd Error: %s" % e )
        raise
    return webHandle
#------------------------------------------------
def controlThermo(whichOne, command):
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    c.execute("select address from thermostats "
        "where location=?; ", (whichOne,))
    thermoIp = c.fetchone()
    dbconn.close
    website = openSite("HTTP://" + thermoIp[0] + "/" + command)
    websiteHtml = website.read()
    return  websiteHtml
    
def getThermoStatus(whichOne):
    website = openSite("HTTP://" + whichOne[0] + "/status")
    # now read the status that came back from it
    websiteHtml = website.read()
    # After getting the status from the little web server on
    # the arduino thermostat, strip off the trailing cr,lf
    # and separate the values into a list that can
    # be used to tell what is going on
    return  websiteHtml.rstrip().split(",")

def ThermostatStatus():
    # The scheduler will run this as a separate thread
    # so I have to open and close the database within
    # this routine
    #print(time.strftime("%A, %B %d at %H:%M:%S"))
    # open the database and set up the cursor (I don't have a
    # clue why a cursor is needed)
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    for whichOne in ['North', 'South']:
        c.execute("select address from thermostats "
            "where location=?; ", (whichOne,))
        thermoIp = c.fetchone()
        try:
            status = getThermoStatus(thermoIp)
        except:
            break
        #print whichOne + " reports: " + str(status)
        c.execute("update thermostats set 'temp-reading' = ?, "
                "status = ?, "
                "'s-temp' = ?, "
                "'s-mode' = ?, "
                "'s-fan' = ?, "
                "peak = ?,"
                "utime = ?"
                "where location = ?;",
                    (status[0],status[1],
                    status[2],status[3],
                    status[4],status[5],
                    time.strftime("%A, %B, %d at %H:%M:%S"),
                    whichOne))
        dbconn.commit()
    dbconn.close()
'''
this is a call back function for the XBee network.  When a message
comes in this function will get the data and put it on a queue.
That's literally all that the separate thread for the XBee library 
does.  Sending and decoding the packets is handled by the main thread
'''
def message_received(data):
    packets.put(data, block=False)
    #print 'gotta packet' 

def sendPacket(where, what):
    # I'm only going to send the absolute minimum. 
    #lprint ("sending to ", ':'.join(hex(ord(x))[2:] for x in where), what)
    zb.send('tx',
        dest_addr_long = where,
        # I always use the 'unknown' value for this
        # it's too much trouble to keep track of two
        # addresses for the device
        dest_addr = UNKNOWN,
        data = what)
'''
OK, another thread has caught the packet from the XBee network,
put it on a queue, this process has taken it off the queue and 
passed it to this routine, now we can take it apart and see
what is going on ... whew!
'''
def handlePacket(data):
    global CurrentPower, DayMaxPower, DayMinPower
    global CurrentOutTemp, DayOutMaxTemp, DayOutMinTemp

    #print data # for debugging so you can see things
    # this packet is returned every time you do a transmit
    # (can be configured out), to tell you that the XBee
    # actually send the darn thing
    if data['id'] == 'tx_status':
        if ord(data['deliver_status']) != 0:
            print 'Transmit error = ',
            print data['deliver_status'].encode('hex')
    # The receive packet is the workhorse, all the good stuff
    # happens with this packet.
    elif data['id'] == 'rx': 
        rxList = data['rf_data'].split(',')
        
        if rxList[0] == 'Status': #This is the status send by the old controller
            # remember, it's sent as a string by the XBees
            #print("Got Old Controller Status Packet")
            tmp = int(rxList[1]) # index 1 is current power
            if tmp > 0:  # Things can happen to cause this
                # and I don't want to record a zero
                CurrentPower = tmp
                DayMaxPower = max(DayMaxPower,tmp)
                DayMinPower = min(DayMinPower,tmp)
                tmp = int(rxList[3]) # index 3 is outside temp
                CurrentOutTemp = tmp
                DayOutMaxTemp = max(DayOutMaxTemp, tmp) 
                DayOutMinTemp = min(DayOutMinTemp, tmp)
                dbconn = sqlite3.connect(DATABASE)
                c = dbconn.cursor()
                # do database stuff
                c.execute("update housestatus " 
                    "set curentpower = ?, "
                    "daymaxpower = ?,"
                    "dayminpower = ?,"
                    "currentouttemp = ?,"
                    "dayoutmaxtemp = ?,"
                    "dayoutmintemp = ?,"
                    "utime = ?;",
                    (CurrentPower, DayMaxPower, DayMinPower,
                    CurrentOutTemp, DayOutMaxTemp,
                    DayOutMinTemp,
                    time.strftime("%A, %B, %d at %H:%M:%S")))
                dbconn.commit()
                dbconn.close()
        elif rxList[0] == 'AcidPump':
            # This is the Acid Pump Status packet
            # it has 'AcidPump,time_t,status,level,#times_sent_message
            # I only want to save status, level, and the last
            # time it reported in to the database for now
            #print("Got Acid Pump Packet")
            dbconn = sqlite3.connect(DATABASE)
            c = dbconn.cursor()
            c.execute("update acidpump set status = ?, "
                "'level' = ?,"
                "utime = ?;",
                (rxList[2], rxList[3],
                time.strftime("%A, %B, %d at %H:%M:%S")))
            dbconn.commit()
            dbconn.close()
        elif rxList[0] == '?\r': #incoming request for a house status message
            # Status message that is broadcast to all devices consists of:
            # power,time_t,outsidetemp,insidetemp,poolmotor  ---more to come someday
            # all fields are ascii with poolmotor being {Low,High,Off}
            #print("Got Status Request Packet")
            dbconn = sqlite3.connect(DATABASE)
            c = dbconn.cursor()
            spower = int(float(c.execute("select rpower from power").fetchone()[0]))
            stime = int((time.time() - (7*3600)))
            sotemp = int(c.execute("select currenttemp from xbeetemp").fetchone()[0])
            sitemp = int(c.execute("select avg(\"temp-reading\") from thermostats").fetchone()[0])
            spoolm = c.execute("select motor from pool").fetchone()[0]
            dbconn.close()
            sstring = "Status,%d,%d,%d,%d,%s\r" %(spower,stime,sotemp,sitemp,spoolm)
            #print sstring.encode('ascii','ignore') #for debugging
            sendPacket(BROADCAST, sstring.encode('ascii','ignore'))
        elif rxList[0] == 'Time':
            #print("Got Time Packet")
            pass
        elif rxList[0] == 'Garage':
            #print("Got Garage Packet")
            #print(rxList)
            if len(rxList) > 2: #this means it's a status from the garage
                                # not a command to the garage
                #print "updating garage in database"
                # Now stick it in the database
                dbconn = sqlite3.connect(DATABASE)
                c = dbconn.cursor()
                c.execute("update garage set door1 = ?, "
                    "door2 = ?,"
                    "waterh = ?,"
                    "utime = ?;",
                    (rxList[1], rxList[2],rxList[3].rstrip(),
                    time.strftime("%A, %B, %d at %H:%M:%S")))
                dbconn.commit()
                dbconn.close()
        elif rxList[0] == 'Pool':
            #print("Got Pool Packet")
            #print(rxList)
            motor = rxList[1].split(' ')[1]
            waterfall = rxList[2].split(' ')[1]
            light = rxList[3].split(' ')[1]
            fountain = rxList[4].split(' ')[1]
            solar = rxList[5].split(' ')[1]
            ptemp = rxList[6].split(' ')[1]
            atemp = rxList[7].split(' ')[1]
            dbconn = sqlite3.connect(DATABASE)
            c = dbconn.cursor()
            c.execute("update pool set motor = ?, "
                "waterfall = ?,"
                "light = ?,"
                "fountain = ?,"
                "solar = ?,"
                "ptemp = ?,"
                "atemp = ?,"
                "utime = ?;",
                (motor, waterfall, light, fountain, 
                solar, ptemp, atemp,
                time.strftime("%A, %B, %d at %H:%M:%S")))
            dbconn.commit()
            dbconn.close()
        elif rxList[0] == 'Power':
            #print("Got Power Packet")
            #print(rxList)
            # I didn't really need to put these into variables, 
            # I could have used the strings directly, but when
            # I came back in a year or two to this code, I 
            # wouldn't have a clue what was going on.  By 
            # putting them in variables (less efficient), I 
            # make my life easier in the future.
            rpower = float(rxList[1])
            CurrentPower = rpower
            DayMaxPower = max(DayMaxPower,CurrentPower)
            DayMinPower = min(DayMinPower,CurrentPower)
            apower = float(rxList[2])
            pfactor = float(rxList[3])
            voltage = float(rxList[4])
            current = float(rxList[5])
            frequency = float(rxList[6].rstrip())
            #print ('rpower %s, apower %s, pfactor %s, voltage %s, current %s, frequency %s' 
            #   %(rpower, apower, pfactor, voltage, current, frequency))
            try:
                dbconn = sqlite3.connect(DATABASE)
                c = dbconn.cursor()
                c.execute("update power set rpower = ?, "
                    "apower = ?,"
                    "pfactor = ?,"
                    "voltage = ?,"
                    "current = ?,"
                    "frequency = ?,"
                    "utime = ?;",
                    (rpower, apower, pfactor, voltage, current, 
                    frequency, time.strftime("%A, %B, %d at %H:%M:%S")))
                dbconn.commit()
            except:
                print "Error: Database error"
            dbconn.close()
        elif rxList[0] == 'Septic':
            #print("Got Septic Packet")
            #print(rxList)
            dbconn = sqlite3.connect(DATABASE)
            c = dbconn.cursor()
            c.execute("update septic set level = ?, utime = ?;",
                (rxList[1].rstrip(), time.strftime("%A, %B, %d at %H:%M:%S")))
            dbconn.commit()
            dbconn.close()
        elif rxList[0] == 'Freezer':
            pass
            #lprint ("Got a Freezer Packet", rxList)
        else:
            print ("Error: can\'t handle " + rxList[0] + ' yet')
            for item in rxList:
                print item,
            print
            pass
    elif data['id'] == 'rx_io_data_long_addr':
        #print ('Got Outside Thermometer Packet')
        tmp = data['samples'][0]['adc-1']
        # Don't even ask about the calculation below
        # it was a real pain in the butt to figure out
        otemp = (((tmp * 1200.0) / 1024.0) / 10.0) * 2.0
        CurrentOutTemp = otemp
        DayOutMaxTemp = max(DayOutMaxTemp, CurrentOutTemp)  
        DayOutMinTemp = min(DayOutMinTemp, CurrentOutTemp)
        dbconn = sqlite3.connect(DATABASE)
        c = dbconn.cursor()
        c.execute("update xbeetemp set 'currenttemp' = ?, "
            "utime = ?;",
            (int(otemp),
            time.strftime("%A, %B, %d at %H:%M:%S")))
        dbconn.commit()
        dbconn.close()
    else:
        print ('Error: Unimplemented XBee frame type ' + data['id'])

#-------------------------------------------------

# This little status routine gets run by scheduler
# periodically to simply put a message in the log file.
# This helps me keep track of what's going on.
def printHouseData():
    lprint('Power Data: Current %s, Min %s, Max %s'
        %(int(float(CurrentPower)), int(float(DayMinPower)), int(float(DayMaxPower))))
    lprint('Outside Temp: Current %s, Min %s, Max %s'
        %(int(float(CurrentOutTemp)), int(float(DayOutMinTemp)), int(float(DayOutMaxTemp))))
    print


def handleCommand(command):
    lprint(command)
    # Commands come in as something like 'Pool lighton'
    c = str(command[0]).split(' ')
    # now it's a list like ["Pool", "lighton"]
    # which is really ['device', 'command']
    # so separate the two and act on them.
    #print repr(c)
    device = c[0]
    todo = c[1].strip(' ')
    if device == 'AcidPump':
        lprint ("AcidPump command", todo)
        if (todo == "pumpOn"):
            lprint ("pump on")
            sendPacket(BROADCAST, "AcidOn\r")
        elif (todo == "pumpOff"):
            lprint ("pump off")
            sendPacket(BROADCAST, "AcidOff\r")
        elif (todo == "AcidStatus"):
            lprint ("pump status")
            sendPacket(BROADCAST, "AcidStatus\r")
        else:
            lprint ("can't do this yet")
    elif device == 'Pool':
        lprint ("Pool command: ", todo)
        if (todo == "lighton"):
            lprint ("lighton")
            sendPacket(BROADCAST, "pool,L\r")
        elif (todo == "lightoff"):
            lprint ("lightoff")
            sendPacket(BROADCAST, "pool,l\r")
        elif (todo == "waterfallon"):
            lprint ("waterfall on")
            sendPacket(BROADCAST, "pool,W\r")
        elif (todo == "waterfalloff"):
            lprint ("waterfall off")
            sendPacket(BROADCAST, "pool,w\r")
        elif (todo == "fountainon"):
            lprint ("fountain on")
            sendPacket(BROADCAST, "pool,F\r")
        elif (todo == "fountainoff"):
            lprint ("fountain off")
            sendPacket(BROADCAST, "pool,f\r")
        elif (todo == "pumpoff"):
            lprint ("pump off")
            sendPacket(BROADCAST, "pool,o\r")
        elif (todo == "pumphigh"):
            lprint ("pump high")
            sendPacket(BROADCAST, "pool,S\r")
        elif (todo == "pumplow"):
            lprint ("pump low")
            sendPacket(BROADCAST, "pool,s\r")
        elif (todo == "controlreset"):
            lprint ("control reset")
            sendPacket(BROADCAST, "pool,b\r")
        else:
            lprint ("haven't done this yet", device, todo)
    elif device == 'Garage':
        lprint ("Garage command", todo)
        if (todo == 'waterhon'):
            sendPacket(BROADCAST, "Garage,waterheateron\r")
        elif (todo == 'waterhoff'):
            sendPacket(BROADCAST, "Garage,waterheateroff\r")
        elif (todo == 'door1open'):
            sendPacket(BROADCAST, "Garage,door1\r")
        elif (todo == 'door1close'):
            sendPacket(BROADCAST, "Garage,door1\r")
        elif (todo == 'door2open'):
            sendPacket(BROADCAST, "Garage,door2\r")
        elif (todo == 'door2close'):
            sendPacket(BROADCAST, "Garage,door2\r")
        else:
            lprint ("haven't done this yet")
    # presets are what other folk call 'scenes'. Where you want
    # several things to happen based on a single command.  Turn off 
    # the lights, turn down the thermostat, lock the door, etc.
    elif device == "preset":
        if (todo == "test"): # This is only to test the interaction
            lprint ("got a preset test command")
        elif (todo =='acoff'):
            controlThermo("North", "off")
            controlThermo("South", "off")
            controlThermo("North", "fan=auto")
            controlThermo("South", "fan=auto")
        elif (todo == 'recirc'):
            controlThermo("North", "fan=recirc")
            controlThermo("South", "fan=recirc")
        elif (todo == 'auto'):
            controlThermo("North", "fan=auto")
            controlThermo("South", "fan=auto")
        elif (todo == 'temp98'):
            controlThermo("North", "temp=98")
            controlThermo("South", "temp=98")
            controlThermo("North", "fan=auto")
            controlThermo("South", "fan=auto")
        elif (todo == 'summernight'):
            controlThermo("North", "temp=78")
            controlThermo("South", "temp=79")
            controlThermo("North", "fan=recirc")
            controlThermo("South", "fan=recirc")
            controlThermo("North", "cool")
            controlThermo("South", "cool")
        elif (todo == 'winternight'):
            controlThermo("North", "temp=73")
            controlThermo("South", "temp=72")
            controlThermo("North", "fan=recirc")
            controlThermo("South", "fan=recirc")
            controlThermo("North", "heat")
            controlThermo("South", "heat")
        elif (todo == 'peakno'):
            controlThermo("North", "peakoff")
            controlThermo("South", "peakoff")
        elif (todo == 'peakyes'):
            controlThermo("North", "peakon")
            controlThermo("South", "peakon")
        else:
            lprint ("haven't done this yet")
    else:
        lprint ("command not implemented: ", str(c))
        
def doComm():
    if packets.qsize() > 0:
        # got a packet from recv thread
        # See, the receive thread gets them
        # puts them on a queue and here is
        # where I pick them off to use
        newPacket = packets.get_nowait()
        # now go dismantle the packet
        # and use it.
        handlePacket(newPacket)
'''
This is where the control interface for the tiny web server is 
defined.  Each of these is a web 'page' that you get to with
an HTTP get request.  Some have parameters, some don't.  Some
hand back data, others don't.  Just think of the as web pages.
'''
class monitorhouseSC(object):
    
    @cherrypy.expose
    def pCommand(self, command):
        handleCommand((command,0));

    @cherrypy.expose
    def index(self):
        status = "<strong>House Monitor Process</strong><br /><br />"
        status += "is actually alive<br />"
        status += ('Power Data: Current %s, Min %s, Max %s<br />'
            %(int(float(CurrentPower)), int(float(DayMinPower)), int(float(DayMaxPower))))
        status += ('Outside Temp: Current %s, Min %s, Max %s<br />'
            %(int(float(CurrentOutTemp)), int(float(DayOutMinTemp)), int(float(DayOutMaxTemp))))
        status += "<br />"
        return status
'''
This is necessary since I have multiple threads running out there 
This function is subscribed to the 'exit' published by the CherryPy
web server and will be called whenever the server is told to exit.
'''      
def gracefulEnd():
    lprint("****************************got to gracefulEnd")
    scheditem.shutdown(wait=False) # shut down the apscheduler
    # halt() must be called before closing the serial
    # port in order to ensure proper thread shutdown
    # for the xbee thread
    zb.halt() # shut down the XBee receive thread
    ser.close()

#-----------------------------------------------------------------
# get the stuff from the houserc file
hv = getHouseValues()
#------------ XBee Stuff -------------------------
XBEEPORT = hv["xbeeport"]
packets = Queue.Queue() # When I get a packet, I put it on here
# Open serial port for use by the XBee
XBEEBAUD_RATE = 9600
ser = serial.Serial(XBEEPORT, XBEEBAUD_RATE)

# the database where I'm storing stuff
DATABASE = hv["database"]
# Get the ip address and port number you want to use
# from the houserc file
ipAddress= hv["monitorhouse"]["ipAddress"]
port = hv["monitorhouse"]["port"]

# The XBee addresses I'm dealing with
BROADCAST = '\x00\x00\x00\x00\x00\x00\xff\xff'
UNKNOWN = '\xff\xfe' # This is the 'I don't know' 16 bit address

#-------------------------------------------------
logging.basicConfig()

# Create XBee library API object, which spawns a new thread
zb = ZigBee(ser, callback=message_received)

#This is the main thread.  Since most of the real work is done by 
# scheduled tasks, this code checks to see if packets have been 
# captured and calls the packet decoder

# This process also handles commands sent over the XBee network 
# to the various devices.  I want to keep the information on the
# exact commands behind the fire wall, so they'll come in as 
# things like 'AcidPump, on', 'Garage, dooropen'
# since this is a multiprocess environment, I'm going to use 
# system v message queues to pass the commands to this process

# Create the message queue where commands can be read
# I just chose an identifier of 12.  It's my machine and I'm
# the only one using it so all that crap about unique ids is
# totally useless.  12 is the number of eggs in a normal carton.

# a priming read for the thermostats
ThermostatStatus()
#------------------Stuff I schedule to happen -----
scheditem = BackgroundScheduler()

# every 30 seconds print the most current power info
# This only goes into the job log so I can see that
# the device is alive and well.
scheditem.add_job(printHouseData, 'interval', seconds=30)
# schedule reading the thermostats for every thirty seconds
scheditem.add_job(ThermostatStatus, 'interval', seconds=10)
scheditem.start()

firstTime = True;
lprint ("Started")
# Now configure the cherrypy server using the values
cherrypy.config.update({'server.socket_host' : ipAddress,
                        'server.socket_port': port,
                        'engine.autoreload_on': False,
                        })
# Subscribe to the 'main' channel in cherrypy to read the command queue
cherrypy.engine.subscribe("main", doComm);
# This subscribe will catch the exit then shutdown the XBee
# read and the apscheduler for a nice exit.
cherrypy.engine.subscribe("exit", gracefulEnd);

try:
    lprint ("Hanging on the wait for HTTP messages")
    # Now just hang on the HTTP server looking for something to 
    # come in.  The cherrypy dispatcher will update the things that
    # are subscribed which will handle other things
    cherrypy.quickstart(monitorhouseSC())
except KeyboardInterrupt:
    print "******************Got here from a user abort"
    gracefulend()
    sys.exit("Told to shut down");

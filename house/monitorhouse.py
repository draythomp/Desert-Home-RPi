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
import MySQLdb as mdb
import sys, os
import urllib2
import BaseHTTPServer
import shlex
import cherrypy
import json
import paho.mqtt.client as mqtt

from houseutils import getHouseValues, lprint, dbTime, dbTimeStamp
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
        lprint(url)
        lprint ("Odd Error: %s" % e )
        raise
    return webHandle
    
def talkHTML(ip, command):
    website = openSite("HTTP://" + ip + '/' + urllib2.quote(command, safe="%/:=&?~#+!$,;'@()*[]"))
    # now (maybe) read the status that came back from it
    if website is not None:
        websiteHtml = website.read()
        return  websiteHtml

    
#------------------------------------------------
def controlThermo(whichOne, command):
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        hc.execute("select address from thermostats "
            "where location=%s; ", (whichOne,))
        thermoIp = hc.fetchone()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close
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
    # open the database and set up the cursor 
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        for whichOne in ['North', 'South']:
            hc.execute("select address from thermostats "
                "where location=%s; ", (whichOne,))
            thermoIp = hc.fetchone()
            try:
                status = getThermoStatus(thermoIp)
            except:
                break
            #print whichOne + " reports: " + str(status)
            hc.execute("update thermostats set `temp-reading` = %s, "
                    "status = %s, "
                    "`s-temp` = %s, "
                    "`s-mode` = %s, "
                    "`s-fan` = %s, "
                    "peak = %s,"
                    "utime = %s"
                    "where location = %s;",
                        (status[0],status[1],
                        status[2],status[3],
                        status[4],status[5],
                        dbTimeStamp(),
                        whichOne))
            hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()
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

    # Send the packet to mqtt for debugging if needed
    packet = ""
    for key, value in data.iteritems():
        if key in ["rf_data","id"]:
            packet += key + " "
            packet += value + ", "
        else:
            packet += key + " "
            packet += "".join("%02x " % ord(b) for b in data[key]) + ", "
    err = mqttc.publish("Desert-Home/XBee/Receive",packet)
    if err[0] != 0:
        lprint("got error {} on publish".format(err[0]))
    #print packet
    #print data # for debugging so you can see things
    # this packet is returned every time you do a transmit
    # (can be configured out), to tell you that the XBee
    # actually sent the darn thing
    if data['id'] == 'tx_status':
        if ord(data['deliver_status']) != 0:
            if data['deliver_status'] != 0x26: #this error happens often
                print 'Transmit error = ', #show the other errors
                print data['deliver_status'].encode('hex')
            #print data
    # The receive packet is the workhorse, all the good stuff
    # happens with this packet.
    elif data['id'] == 'rx':
        # First, try for the new JSON format from the
        # device.  I'm converting them one at a time
        # to send JSON strings to the house controller
        try:
            #print data['rf_data']
            jData = json.loads(data['rf_data'][:-1])
            if "TempSensor" in jData.keys():
                #lprint("Temp Sensor Packet:", jData)
                #lprint(jData)
                #pass this off to the mqtt server
                err = mqttc.publish("Desert-Home/Device/TempSensor",data['rf_data'][:-1],retain=True);
                if err[0] != 0:
                    lprint("got error {} on publish".format(err[0]))
            if "Barometer" in  jData.keys():
                #print jData
                # pass this off to the mqtt server
                # I put a cr at the end so it displays nicely on arduino
                err = mqttc.publish("Desert-Home/Device/Barometer",data['rf_data'][:-1],retain=True);
                if err[0] != 0:
                    lprint("got error {} on publish".format(err[0]))
            if "PowerMon" in  jData.keys():
                #print jData
                err = mqttc.publish("Desert-Home/Device/PowerMon",data['rf_data'][:-1],retain=True);
                if err[0] != 0:
                    lprint("got error {} on publish".format(err[0]))
        except mdb.Error, e:
            lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
            return
        except KeyError:
            lprint("KeyError doing json decode")
            lprint(jData)
            return
        except AttributeError, e:
            lprint ("AttributeError, json decode")
            lprint(data)
            return
        except ValueError: # Old style Data received
            rxList = data['rf_data'].split(',')
            
            if rxList[0] == 'Status': #This was the status send by the old controller
                pass
            elif rxList[0] == 'AcidPump':
                # I finally gave up on having this
                # I just drop a chlorine tablet in the
                # pool when I check the skimmer.
                pass
            elif rxList[0] == '?\r': #incoming request for a house status message
                # Status message that is broadcast to all devices consists of:
                # power,time_t,outsidetemp,insidetemp,poolmotor  ---more to come someday
                # all fields are ascii with poolmotor being {Low,High,Off}
                #print("Got Status Request Packet")
                spoolm = 1
                # Collect data from the two databases involved
                try:
                    hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
                    hc = hdbconn.cursor()
                    # The last power reading taken
                    hc.execute("select rpower from power order by utime desc limit 1")
                    spower = int(float(hc.fetchone()[0]))
                    # The last report from the pool
                    hc.execute("select motor from pool")
                    spoolm = hc.fetchone()[0]
                    hc.execute("select avg(`temp-reading`) from thermostats")
                    sitemp = int(hc.fetchone()[0])
                except mdb.Error, e:
                    lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
                hdbconn.close()
                
                # now the weather station mysql database
                try:
                    wdbconn = mdb.connect(host=wdbHost, user=wdbUser, passwd=wdbPassword, db=wdbName)
                    wc = wdbconn.cursor()
                    # The outside temperature is held in weather (naturally)
                    wc.execute("select reading from ftemperature where utime = "
                        "(select max(utime) from ftemperature);")
                    sotemp = int(wc.fetchone()[0])
                except mdb.Error, e:
                    lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
                wdbconn.close()
                
                # and finally stuff that is live, like the time
                stime = int((time.time() - time.timezone))
                
                # I can finally construct the reply
                sstring = "Status,%d,%d,%d,%d,%s\r" %(spower,stime,sotemp,sitemp,spoolm)
                #print sstring.encode('ascii','ignore') #for debugging
                sendPacket(BROADCAST, sstring.encode('ascii','ignore'))
            elif rxList[0] == 'Time':
                #print("Got Time Packet")
                pass
            elif rxList[0] == 'Garage':
                print("Got Garage Packet")
                err = mqttc.publish("Desert-Home/Device/Garage",data['rf_data'][:-1],retain=True);
                if err[0] != 0:
                    lprint("got error {} on publish".format(err[0]))
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
                try:
                    hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
                    hc = hdbconn.cursor()
                    hc.execute("update pool set motor = %s, "
                        "waterfall = %s,"
                        "light = %s,"
                        "fountain = %s,"
                        "solar = %s,"
                        "ptemp = %s,"
                        "atemp = %s,"
                        "utime = %s;",
                        (motor, waterfall, light, fountain, 
                        solar, ptemp, atemp,
                        dbTimeStamp()))
                    hdbconn.commit()
                except mdb.Error, e:
                    lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
                hdbconn.close()
            elif rxList[0] == 'Septic':
                #print("Got Septic Packet")
                #print(rxList)
                try:
                    hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
                    hc = hdbconn.cursor()
                    hc.execute("update septic set level = %s, utime = %s;",
                        (rxList[1].rstrip(), dbTimeStamp()))
                    hdbconn.commit()
                except mdb.Error, e:
                    lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
                hdbconn.close()
            elif rxList[0] == 'HouseFreezer':
                #print("monitorhouse got Freezer Packet")
                #print(rxList)
                # Convert the string received into a json string for sending
                # to mqtt for the savehouse process
                #print (json.dumps({"housefreezer":{"temperature":rxList[3][:-1],
                #    "defroster":rxList[2],
                #    "utime": dbTimeStamp()}}) )
                err = mqttc.publish("Desert-Home/Device/HouseFreezer",
                    json.dumps({"housefreezer":{"temperature":rxList[3][:-1],
                    "defroster":rxList[2],
                    "utime": dbTimeStamp()}}),
                    retain=True);
                if err[0] != 0:
                    lprint("got error {} on publish".format(err[0]))
            elif rxList[0] == 'HouseFridge':
                #print("monitorhouse got Fridge Packet")
                #print(rxList)
                # Convert the string received into a json string for sending
                # to mqtt for the savehouse process
                #print (json.dumps({"housefridge":{"temperature":rxList[2][:-1],
                #    "utime": dbTimeStamp()}}) )
                err = mqttc.publish("Desert-Home/Device/HouseFridge",
                    json.dumps({"housefridge":{"temperature":rxList[2][:-1],
                    "utime": dbTimeStamp()}}),
                    retain=True);
                if err[0] != 0:
                    lprint("got error {} on publish".format(err[0]))
            elif rxList[0] == 'GarageFreezer':
                #print("monitorhouse got Garage Freezer Packet")
                #print(rxList)
                # Convert the string received into a json string for sending
                # to mqtt for the savehouse process
                #print (json.dumps({"garagefreezer":{"temperature":rxList[2][:-1],
                #    "utime": dbTimeStamp()}}) )
                err = mqttc.publish("Desert-Home/Device/GarageFreezer",
                    json.dumps({"garagefreezer":{"temperature":rxList[2][:-1],
                    "utime": dbTimeStamp()}}),
                    retain=True);
                if err[0] != 0:
                    lprint("got error {} on publish".format(err[0]))
            else:
                print ("Error: can\'t handle " + rxList[0] + ' yet')
                for item in rxList:
                    print item,
                print
                pass
    elif data['id'] == 'rx_io_data_long_addr': # saving this in case I need one
        #print ('i/o data packet')
        pass
    else:
        print ('Error: Unimplemented XBee frame type ' + data['id'])

#-------------------------------------------------

def logIt(text):
    mqttc.publish("Desert-Home/Log","{}, {}".format(processName, text));
    
# This little status routine gets run by scheduler
# periodically to simply put a message in the log file.
# This helps me keep track of what's going on.
def printHouseData():
    lprint("I'm alive")
    logIt("I'm alive")

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
    elif device == 'Freezer':
        lprint ("Freezer command", todo)
        if (todo == 'defroston'):
            sendPacket(BROADCAST, "Freezer,DefrostOn\r")
        elif (todo == 'defrostoff'):
            sendPacket(BROADCAST, "Freezer,DefrostOff\r")
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
hand back data, others don't.  Just think of them as web pages.
'''
class monitorhouseSC(object):
    
    @cherrypy.expose
    def pCommand(self, command):
        handleCommand((command,0));

    @cherrypy.expose
    def index(self):
        status = "<strong>House Monitor Process</strong><br /><br />"
        status += "is actually alive<br />"
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

# the database where I'm storing house stuff
hdbName = hv["houseDatabase"]
hdbHost = hv["houseHost"]
hdbPassword = hv["housePassword"]
hdbUser = hv["houseUser"]
# weather database
wdbName = hv["weatherDatabase"]
wdbHost = hv["weatherHost"]
wdbPassword = hv["weatherPassword"]
wdbUser = hv["weatherUser"]

# Now the mqtt server that will be used
processName = os.path.basename(sys.argv[0])
mqttc = mqtt.Client(client_id=processName)
mqttServer = hv["mqttserver"]
mqttc.connect(mqttServer, 1883, 60)
mqttc.loop_start()

# Get the ip address and port number you want to use
# from the houserc file
ipAddress= hv["monitorhouse"]["ipAddress"]
port = hv["monitorhouse"]["port"]
irisControl = hv["iriscontrol"]["ipAddress"] + ":" + \
                    str(hv["iriscontrol"]["port"])
lprint("Iris Control is:", irisControl);

wemoControl = hv["wemocontrol"]["ipAddress"] + ":" + \
                    str(hv["wemocontrol"]["port"])
lprint("Wemo Control is:", wemoControl);

# The XBee addresses I'm dealing with
BROADCAST = '\x00\x00\x00\x00\x00\x00\xff\xff'
UNKNOWN = '\xff\xfe' # This is the 'I don't know' 16 bit address

#-------------------------------------------------
logging.basicConfig()

# Create XBee library API object, which spawns a new thread
# that receives the XBee messages.
zb = ZigBee(ser, callback=message_received)

# a priming read for the thermostats
ThermostatStatus()
#------------------Stuff I schedule to happen -----
scheditem = BackgroundScheduler()

# every 30 seconds print the most current power info
# This only goes into the job log so I can see that
# the device is alive and well.
scheditem.add_job(printHouseData, 'interval', seconds=300)
# schedule reading the thermostats for every few seconds
scheditem.add_job(ThermostatStatus, 'interval', seconds=10, max_instances=2)
scheditem.start()

lprint ("Started")
# Now configure the cherrypy server using the values
cherrypy.config.update({'server.socket_host' : ipAddress.encode('ascii','ignore'),
                        'server.socket_port': port,
                        'engine.autoreload.on': False,
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

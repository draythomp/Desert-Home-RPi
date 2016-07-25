#! /usr/bin/python
'''
This saves data gathered for various devices using mqtt to
a database on my house NAS.
'''
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import datetime
import time
import signal
import MySQLdb as mdb
import sys, os
import shlex
import json
import urllib2
import paho.mqtt.client as mqtt

from houseutils import getHouseValues, lprint, dbTime, dbTimeStamp

def openSite(Url):
    #print Url
    try:
        webHandle = urllib2.urlopen(Url, timeout=10) #if it doesn't answer in 5 seconds, it won't
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
        lprint(Url)
        lprint ("Odd Error: %s" % e )
        raise
    return webHandle
    
def talkHTML(ip, command):
    website = openSite("HTTP://" + ip + '/' + urllib2.quote(command, safe="%/:=&?~#+!$,;'@()*[]"))
    # now (maybe) read the status that came back from it
    if website is not None:
        websiteHtml = website.read()
        return  websiteHtml

def handleTempSensor(data):
    try:
        jData = json.loads(data)
    except ValueError as err:
        lprint(err)
        lprint("The buffer:")
        lprint(str(msg.payload))
        return
    #print jData
    #print "name       : ", jData["TempSensor"]["name"]
    #print "command    : ", jData["TempSensor"]["command"]
    #print "processor V: ", jData["TempSensor"]["voltage"]
    #print "room  T    : ", jData["TempSensor"]["temperature"]
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, 
            passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        hc.execute("select count(*) from tempsensor where name = %s;", 
            (jData['TempSensor']['name'],))
        count = hc.fetchone()[0]
        if count == 0:
            lprint ("Adding new tempSensor")
            hc.execute("insert into tempsensor(name,"
                "pvolt, temp, utime)"
                "values (%s, %s, %s, %s);",
                (jData["TempSensor"]["name"],
                jData["TempSensor"]["voltage"],
                jData["TempSensor"]["temperature"],
                dbTimeStamp()))
        else:
            #lprint ("updating tempsensor ", jData['TempSensor']['name'])
            hc.execute("update tempsensor set " 
                "pvolt = %s,"
                "temp = %s,"
                "utime = %s where name = %s ;",
                (jData['TempSensor']['voltage'],
                jData['TempSensor']['temperature'],
                dbTimeStamp(), 
                jData['TempSensor']['name']
                ))
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()
    if (jData['TempSensor']['command'] != 'nothing'):
        lprint("Button Command from sensor")
        #got a command from the sensor
        talkHTML(irisControl,"command?whichone=mbdrm&what=toggle");
        talkHTML(wemoControl,"wemocommand?whichone=patio&what=off");

def handleGarage(data):
    #print("Got Garage")
    #print(data)
    # This is not JSON, it's a comma separated list
    rxList = data.split(',')
    if rxList[0] != 'Garage':
        logIt("published as Garage, but found {}".format(rxList[0]))
    if len(rxList) > 2: #this means it's a status from the garage
                        # not a command to the garage
        #print "updating garage in database"
        # Now stick it in the database
        try:
            hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
            hc = hdbconn.cursor()
            hc.execute("update garage set door1 = %s, "
                "door2 = %s,"
                "waterh = %s,"
                "utime = %s;",
                (rxList[1], rxList[2],rxList[3].rstrip(),
                dbTimeStamp()))
            hdbconn.commit()
        except mdb.Error, e:
            lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        hdbconn.close()

def handlePowerMon(data):
    try:
        jData = json.loads(data)
    except ValueError as err:
        lprint(err)
        lprint("The buffer:")
        lprint(str(msg.payload))
        return
    #print jData
    rpower = jData["PowerMon"]["RP"]
    apower = jData["PowerMon"]["AP"]
    pfactor = jData["PowerMon"]["PF"]
    voltage = jData["PowerMon"]["V"]
    current = jData["PowerMon"]["I"]
    frequency = jData["PowerMon"]["F"]
    #print ('rpower %s, apower %s, pfactor %s, voltage %s, current %s, frequency %s' 
    #   %(rpower, apower, pfactor, voltage, current, frequency))
    #print "updating power in database"
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        hc.execute("update power set rpower = %s, "
            "apower = %s,"
            "pfactor = %s,"
            "voltage = %s,"
            "current = %s,"
            "frequency = %s,"
            "utime = %s;",
            (rpower, apower, pfactor, voltage, current, 
            frequency, dbTimeStamp()))
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()
    
def logIt(text):
    mqttc.publish("Desert-Home/Log","{}, {}".format(processName, text));

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, rc):
    print("Connected with result code "+str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe([("Desert-Home/Device/TempSensor",0),
                    ("Desert-Home/Device/Garage", 0),
                    ("Desert-Home/Device/PowerMon",0)])

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    #print(msg.topic+" "+str(msg.payload))
    if msg.topic == 'Desert-Home/Device/TempSensor':
        logIt("got room temperature sensor")
        handleTempSensor(msg.payload)
    elif msg.topic == 'Desert-Home/Device/Garage':
        logIt("got garage controller")
        handleGarage(msg.payload)
    elif msg.topic == 'Desert-Home/Device/PowerMon':
        logIt("got power monitor")
        handlePowerMon(msg.payload)
    else:
        lprint("got odd topic back: {}".format(msg.topic))
        logIt("got odd topic back: {}".format(msg.topic))

#-----------------------------------------------------------------
# get the stuff from the houserc file
hv = getHouseValues()
# the database where I'm storing house stuff
hdbName = hv["houseDatabase"]
hdbHost = hv["houseHost"]
hdbPassword = hv["housePassword"]
hdbUser = hv["houseUser"]
# the iris switch controller
irisControl = hv["iriscontrol"]["ipAddress"] + ":" + \
                    str(hv["iriscontrol"]["port"])
lprint("Iris Control is:", irisControl);
# the wemo switch controller
wemoControl = hv["wemocontrol"]["ipAddress"] + ":" + \
                    str(hv["wemocontrol"]["port"])
lprint("Wemo Control is:", wemoControl);

#
# Now the mqtt server that will be used
processName = os.path.basename(sys.argv[0])
mqttc = mqtt.Client(client_id=processName, clean_session=True)
mqttServer = hv["mqttserver"]
mqttc.connect(mqttServer, 1883, 60)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
try:
    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    lprint ("Going into the mqtt wait loop")
    mqttc.loop_forever()
except KeyboardInterrupt:
    lprint("Cntl-C from user");
              
lprint(processName,"Done")
sys.stdout.flush()
sys.exit("")
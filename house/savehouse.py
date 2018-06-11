#! /usr/bin/python
'''
This saves data gathered for various devices using mqtt to
a database on my house NAS.
'''
#from apscheduler.schedulers.background import BackgroundScheduler
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

from houseutils import timer, getHouseValues, lprint, dbTime, dbTimeStamp

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
        #lprint ("recording tempsensor ", jData['TempSensor']['name'])
        hc.execute("insert into tempsensor(name,"
            "pvolt, temp, utime)"
            "values (%s, %s, %s, %s);",
            (jData["TempSensor"]["name"],
            jData["TempSensor"]["voltage"],
            jData["TempSensor"]["temperature"],
            dbTimeStamp()))
        hdbconn.commit()
        hdbconn.close()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        hdbconn.close()
    if (jData['TempSensor']['command'] != 'nothing'):
        lprint("Button Command from sensor " )
        #got a command from the sensor
        talkHTML(irisControl,"command?whichone=mbdrm&what=toggle");
        talkHTML(wemoControl,"wemocommand?whichone=patio&what=off");

def handleHouseFreezer(data):
    try:
        jData = json.loads(data)
    except ValueError as err:
        lprint(err)
        lprint("The buffer:")
        lprint(str(msg.payload))
        return
    #print jData
    #print "temp       : ", jData["housefreezer"]["temperature"]
    #print "defroster  : ", jData["housefreezer"]["defroster"]
    #print "utime      : ", jData["housefreezer"]["utime"]
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        whichone = dbTimeStamp()
        hc.execute("insert into housefreezer (temperature, defroster, utime)"
            "values(%s,%s,%s);",
            (jData["housefreezer"]["temperature"],
            jData["housefreezer"]["defroster"],
            whichone))
        hc.execute("select watts from smartswitch where name = 'freezer';")
        watts = hc.fetchone()[0]
        hc.execute("update housefreezer set watts = %s"
            "where utime = %s;",
            (watts, whichone));
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()
    
def handleHouseFridge(data):
    try:
        jData = json.loads(data)
    except ValueError as err:
        lprint(err)
        lprint("The buffer:")
        lprint(str(msg.payload))
        return
    #print jData
    #print "temp       : ", jData["housefridge"]["temperature"]
    #print "utime      : ", jData["housefridge"]["utime"]
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        whichone = dbTimeStamp()
        hc.execute("insert into housefridge (temperature, watts, utime)"
            "values(%s,%s, %s);",
            (jData["housefridge"]["temperature"],
            '0',
            whichone))
        hc.execute("select watts from smartswitch where name = 'refrigerator';")
        watts = hc.fetchone()[0]
        hc.execute("update housefridge set watts = %s"
            "where utime = %s;",
            (watts, whichone));
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()

def handleGarageFreezer(data):
    try:
        jData = json.loads(data)
    except ValueError as err:
        lprint(err)
        lprint("The buffer:")
        lprint(str(msg.payload))
        return
    #print jData
    #print "temp       : ", jData["garagefreezer"]["temperature"]
    #print "utime      : ", jData["garagefreezer"]["utime"]
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        whichone = dbTimeStamp()
        hc.execute("insert into garagefreezer (temperature, watts, utime)"
            "values(%s,%s, %s);",
            (jData["garagefreezer"]["temperature"],
            '0',
            whichone))
        hc.execute("select watts from smartswitch where name = 'garagefreezer';")
        watts = hc.fetchone()[0]
        hc.execute("update garagefreezer set watts = %s"
            "where utime = %s;",
            (watts, whichone));
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()

    
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
#            hc.execute("update garage set door1 = %s, "
#                "door2 = %s,"
#                "waterh = %s,"
#                "utime = %s;",
#                (rxList[1], rxList[2],rxList[3].rstrip(),
#                dbTimeStamp())) 
            hc.execute("insert into garage (door1, door2, waterh, utime)"
                "values(%s, %s, %s, %s);",
                (rxList[1], rxList[2], rxList[3].rstrip(),
                dbTimeStamp() ))
            hdbconn.commit()
        except mdb.Error, e:
            lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        hdbconn.close()

def handleWaterHeater(data):
    print "updating water heater in database"
    try:
        jData = json.loads(data)
    except ValueError as err:
        lprint(err)
        lprint("The buffer:")
        lprint(str(msg.payload))
        return
    print jData
    print "voltage       : ", jData["WaterHeater"]["V"]
    print "current       : ", jData["WaterHeater"]["I"]
    print "power         : ", jData["WaterHeater"]["P"]
    print "energy        : ", jData["WaterHeater"]["E"]
    print "top temp      : ", jData["WaterHeater"]["TT"]
    print "bottom temp   : ", jData["WaterHeater"]["BT"]
    print "power applied : ", jData["WaterHeater"]["PA"]
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        whichone = dbTimeStamp()
        hc.execute("insert into waterheater (voltage, current, power, energy,ttemp,btemp,waterh)"
            "values(%s,%s,%s,%s,%s,%s,%s);",
            (jData["WaterHeater"]["V"],
            jData["WaterHeater"]["I"],
            jData["WaterHeater"]["P"],
            jData["WaterHeater"]["E"],
            jData["WaterHeater"]["TT"],
            jData["WaterHeater"]["BT"],
            jData["WaterHeater"]["PA"]
            ))
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()
       
# power record only gets updated once a minute
rpower = ""
apower = ""
pfactor = ""
voltage = ""
current = ""
frequency = ""

def updatePower():
    #print ('rpower %s, apower %s, pfactor %s, voltage %s, current %s, frequency %s' 
    #  %(rpower, apower, pfactor, voltage, current, frequency))
    #print "updating power in database"
    try:
        hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
        hc = hdbconn.cursor()
        hc.execute("insert into power (rpower, apower, pfactor, voltage, current, frequency, utime)"
            "values(%s,%s,%s,%s,%s,%s,%s);",
            (rpower, apower, pfactor, voltage, current, 
            frequency, dbTimeStamp()))
        hdbconn.commit()
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()
    
# This just saves the data for minute updates to db
def handlePowerMon(data):
    global rpower, apower, pfactor, voltage, current, frequency

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
    
def logIt(text):
    mqttc.publish("Desert-Home/Log","{}, {}".format(processName, text));

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, rc):
    print("Connected with result code "+str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe([("Desert-Home/Device/TempSensor",0),
                    ("Desert-Home/Device/Garage", 0),
                    ("Desert-Home/Device/HouseFreezer",0),
                    ("Desert-Home/Device/HouseFridge",0),
                    ("Desert-Home/Device/GarageFreezer",0),
                    ("Desert-Home/Device/WaterHeater",0),
                    ("Desert-Home/Device/PowerMon",0)])

# The callback for when a PUBLISH message is received from the server.
# Each XBee house device sends (or is interrogated) by monitorhouse which sends
# the data in JSON format to mqtt. This looks at each message and directs it
# to a routine to save the data on my database.
def on_message(client, userdata, msg):
    #print(msg.topic+" "+str(msg.payload))
    if msg.topic == 'Desert-Home/Device/TempSensor':
        logIt("got room temperature sensor")
        handleTempSensor(msg.payload)
    elif msg.topic == 'Desert-Home/Device/Garage':
        logIt("got garage controller")
        handleGarage(msg.payload)
    elif msg.topic == 'Desert-Home/Device/HouseFreezer':
        logIt("got house freezer monitor")
        handleHouseFreezer(msg.payload)
    elif msg.topic == 'Desert-Home/Device/HouseFridge':
        logIt("got house fridge monitor")
        handleHouseFridge(msg.payload)
    elif msg.topic == 'Desert-Home/Device/GarageFreezer':
        logIt("got garage freezer monitor")
        handleGarageFreezer(msg.payload)
    elif msg.topic == 'Desert-Home/Device/PowerMon':
        logIt("got power monitor")
        handlePowerMon(msg.payload)
    elif msg.topic == 'Desert-Home/Device/WaterHeater':
        logIt("got waterheater")
        handleWaterHeater(msg.payload)
    else:
        lprint("got odd topic back: {}".format(msg.topic))
        logIt("got odd topic back: {}".format(msg.topic))
    # update the timer for saving things.
    checkTimer.tick()

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
lprint("Wemo Control is:", wemoControl)

checkTimer = timer(None)

#
# Now the mqtt server that will be used
processName = os.path.basename(sys.argv[0])
mqttc = mqtt.Client(client_id=processName, clean_session=True)
mqttServer = hv["mqttserver"]
mqttc.connect(mqttServer, 1883, 60)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
# one minute timer for updating power record
minute = timer(updatePower, minutes=1)
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
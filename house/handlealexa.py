#!/usr/bin/python
import os
import sys
import time
import paho.mqtt.client as mqtt
import ssl
import json
import pprint
import urllib2
import MySQLdb as mdb
from houseutils import lprint, getHouseValues, timer, checkTimer

pp = pprint.PrettyPrinter(indent=2)

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



def on_awsConnect(client, userdata, flags, rc):
    lprint("mqtt connection to AWSIoT returned result: " + str(rc) )
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed. You still have to do the
    # reconnect in code because that doesn't happen automatically
    client.subscribe ([(awsShadowDelta , 1 ),
                      (awsShadowDocuments, 1)])
                      
# If you want to see the shadow documents to observe what is going on'
# uncomment the prints below.
def on_awsMessage(client, userdata, msg):
    #print "TOPIC = ",
    #print msg.topic
    #print "PAYLOAD = ",
    payload = {}
    payload = json.loads(msg.payload)
    #pp.pprint (payload)
    #print ""
    
    # If you tell alexa to turn off something, it creates a 'desire' as part
    # of the shadow document. The difference between the desire and the reported
    # is called a 'delta' the delta is sent in one message and is handled farther 
    # down below as a command to do something. 
    
    # Right under here I get the entire document and compare the 'desire' part
    # to the corresponding items in the 'reported' part. When I find something in
    # the desire that is the same as something in the reported, I remove the entry
    # from the desire. If you get rid of all the entries in desire, the entire
    # desire part of the document is removed and just disappears until it's 
    # needed later.
    
    # The reason for this is because when the desire stays around and you walk
    # over and change something by hand, AWS will generate a delta because the
    # reported is suddenly different from the desired. That means you open the
    # garage door by hand, aws senses that the desire is closed, sends a delta
    # and closes the garage door on you.
    
    # Fortunately, I discovered this with a light, not a garage door.
        
    if msg.topic == awsShadowDocuments:
        #print "got full thing"
        if "desired" not in payload["current"]["state"]:
            #print "'desired' not there"
            return
        desired = payload["current"]["state"]["desired"]
        reported = payload["current"]["state"]["reported"]
        #pp.pprint (reported)
        #pp.pprint (desired)
        fixit = False
        fixitString = "{ \"state\" : { \"desired\": {"
        for item in desired.keys():
            # when updating this, you'll often encounter
            # items that aren't fully implemented yet
            # this not reported is just to keep from dying
            if not reported.get(item):
                lprint ("found odd item " + item)
                break
            if desired[item] == reported[item]:
                fixit = True
                lprint ("found left over desire at", item)
                fixitString += "\"" + item + "\": null,"
        if not fixit:
            return
        fixitString = fixitString[:-1] #remove the trailing comma JSON doesn't like it
        fixitString +="} } }"
        lprint ("sending:", fixitString)
        err = awsMqtt.publish("$aws/things/house/shadow/update",fixitString)
        if err[0] != 0:
            lprint("got error {} on publish".format(err[0]))
    
    # The 'delta' message is the difference between the 'desired' entry and
    # the 'reported' entry. It's the way of telling me what needs to be changed
    # because I told alexa to do something. What I tell alexa to do goes into
    # the desired entry and the delta is then created and published. Note that
    # the desired is not removed, it has to be done specifically, hence the 
    # code above.
    
    elif msg.topic == awsShadowDelta:
        lprint ("got a delta")
        lprint (pp.pformat(payload["state"]))
        deviceGroup = ""
        for item in payload["state"].keys():
            if item == "westPatioLight":
                command = str(item + ' ' + payload["state"][item])
                deviceGroup = "Wemo"
                sendCommand(deviceGroup, command)
            elif item == "outsideLights":
                command = str(item + ' ' + payload["state"][item])
                deviceGroup = "Wemo"
                sendCommand(deviceGroup, command)
            elif item == "mbLight":
                command = str(item + ' ' + payload["state"][item])
                deviceGroup = "Iris"
                sendCommand(deviceGroup, command)
            elif item == "goodnight":
                # This is a command without a parameter,
                # 'goodnight' means shut the last of the lights off
                # so I don't care about the parameter
                # just take care of the items.
                command = "mbLight off"
                deviceGroup = "Iris"
                sendCommand(deviceGroup, command)
                command = "outsideLights off"
                deviceGroup = "wemo"
                sendCommand(deviceGroup, command)
            # The two thermostats are http devices because I built
            # them early on and didn't know about XBees. Eventually,
            # they will get replaced with a whole house solution
            # that will be on the XBee network. Also, since it was an 
            # early device the commands it uses are strange. This means I 
            # have to fiddle around a LOT composing the commands.
            elif (   item == "nThermoTempSet" 
                  or item == "sThermoTempSet"):
                whichOne = "South"
                if ( item[0] == 'n'):
                    whichOne = 'north'
                command = "temp=" + payload["state"][item]
                print whichOne,command
                controlThermo(whichOne,command)
            elif (   item == "nThermoModeSet" 
                  or item == "sThermoModeSet"):
                whichOne = "South"
                if ( item[0] == 'n'):
                    whichOne = 'north'
                if ( payload["state"][item] == "heating"):
                    command = "heat"
                elif ( payload["state"][item] == "cooling"):
                    command = "cool"
                else:
                    command ="off"
                print whichOne,command
                controlThermo(whichOne,command)
            elif (   item == "nThermoFanSet" 
                  or item == "sThermoFanSet"):
                whichOne = "South"
                if ( item[0] == 'n'):
                    whichOne = 'north'
                if ( payload["state"][item] == "recirc"):
                    command = "fan=recirc"
                elif ( payload["state"][item] == "on"):
                    command = "fan=on"
                else:
                    command ="fan=auto"
                print whichOne,command
                controlThermo(whichOne,command)
            else:
                lprint("I don't know about item ", item)
                return
            
def sendCommand(deviceGroup, command):
    lprint("alexa send to " + deviceGroup + ' ' + command)
    err = dhMqtt.publish("Desert-Home/Command/"+deviceGroup, command)
    if err[0] != 0:
        lprint("got error {} on publish".format(err[0]))
        # This is likely a broken pipe from mqtt timout, just reconnect
        # because AWS will send the message over and over until it is 
        # taken care of.
        dhMqtt.reconnect()

    
def on_dhConnect(client, userdata, flags, rc):
    lprint("mqtt connection to Desert-Home returned result: " + str(rc) )
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed. It doesn't automaticall
    # reconnect, I have to do that separately

def on_dhMessage(client, userdata, msg):
    # This isn't supposed to be receiving messages from the local
    # mqtt server, but I may want to someday, plus this may help with
    # debugging at some point
    lprint (msg.topic)
    print (msg.payload)

# This is on a timer and will get data out of the database and update
# the shadow. It is NOT event driven, so you have to adjust the timer
# interval to your needs.
def updateIotShadow():
    dbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, db=dbName)
    try:
        c = dbconn.cursor()
        c.execute("select reading from ftemperature where utime = "
                "(select max(utime) from ftemperature);")
        temperature = c.fetchone()[0]
        c.execute("select reading from barometer where utime = "
                "(select max(utime) from barometer);")
        barometer = c.fetchone()[0]
        c.execute ("select reading from humidity where utime = "
                "(select max(utime) from humidity);")
        humidity = c.fetchone()[0]
        c.execute("select speed from wind where utime = "
                "(select max(utime) from wind);")
        windSpeed = c.fetchone()[0]
        c.execute("select directionc from wind where utime = "
                "(select max(utime) from wind);")
        windDirectionC = c.fetchone()[0]
        directionStrings = {
        "N":"north",
        "NNE":"north northeast",
        "NE":"northeast",
        "ENE":"east northeast",
        "E":"east ",
        "ESE":"east southeast",
        "SE":"south east",
        "SSE":"south southeast",
        "S":"south",
        "SSW":"south southwest",
        "SW":"southwest",
        "WSW":"west southwest",
        "W":"west",
        "WNW":"west northwest",
        "NW":"northwest",
        "NNW":"north northwest"
        }
        directionString = directionStrings[windDirectionC]
        c.execute("SELECT reading, rdate FROM `raincounter` "
                "where rdate > date_sub(now(), interval 24 hour) "
                "ORDER BY `rdate` asc limit 1"
            )
        startCount = c.fetchone()[0]
        c.execute("select reading  from raincounter where rdate = "
                "(select max(rdate) from raincounter);")
        endCount = c.fetchone()[0]
        rainToday = str((float(endCount) - float(startCount)) * 0.01)
    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    dbconn.close()

    ## Done with the weather, now for devices
    
    hdbconn = mdb.connect(host=hdbHost, user=hdbUser, passwd=hdbPassword, db=hdbName)
    try:
        c = hdbconn.cursor()
        # Controlled Lights
        c.execute('select status from wemo where name="patio";')
        westPatioLight = c.fetchone()[0]
        c.execute('select status from wemo where name="outsidegarage";')
        outsideGarage = c.fetchone()[0]
        c.execute('select status from wemo where name="frontporch";')
        frontPorch = c.fetchone()[0]
        c.execute('select status from wemo where name="cactusspot";')
        cactusSpot = c.fetchone()[0]
        c.execute('select status from smartswitch where name = "mbdrm";')
        mbLight = c.fetchone()[0]
        # Garage Doors
        c.execute('select door1 from garage;')
        gDoor1 = c.fetchone()[0]
        c.execute('select door2 from garage;')
        gDoor2 = c.fetchone()[0]
        # North and South Thermostat Data
        c.execute('select status from thermostats where location="North";')
        nThermoMode= c.fetchone()[0]
        c.execute('select status from thermostats where location="South";')
        sThermoMode= c.fetchone()[0]
        c.execute('select `temp-reading` from thermostats where location="North";')
        nThermoTemp= c.fetchone()[0]
        c.execute('select `temp-reading` from thermostats where location="South";')
        sThermoTemp= c.fetchone()[0]
        c.execute('select `peak` from thermostats where location="North";')
        nThermoPeak= c.fetchone()[0]
        c.execute('select `peak` from thermostats where location="South";')
        sThermoPeak= c.fetchone()[0]
        #North and South thermostat Settings
        c.execute('select `s-mode` from thermostats where location="North";')
        nThermoModeSet= c.fetchone()[0]
        c.execute('select `s-mode` from thermostats where location="South";')
        sThermoModeSet= c.fetchone()[0]
        c.execute('select `s-fan` from thermostats where location="North";')
        nThermoFanSet= c.fetchone()[0]
        c.execute('select `s-fan` from thermostats where location="South";')
        sThermoFanSet= c.fetchone()[0]
        c.execute('select `s-temp` from thermostats where location="North";')
        nThermoTempSet= c.fetchone()[0]
        c.execute('select `s-temp` from thermostats where location="South";')
        sThermoTempSet= c.fetchone()[0]

    except mdb.Error, e:
        lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
    hdbconn.close()
    
    # are any of the controlled outside lights on?
    outsideLightsList = [cactusSpot, frontPorch, outsideGarage]
    outsideLights = "off"
    for item in outsideLightsList:
        if item.lower() == "on":
            outsideLights = "on"
            
    # Create report in JSON format; this should be an object, etc.
    # but for now, this will do.
    report = "{ \"state\" : { \"reported\": {"
    report += "\"temp\": \"%s\", " %(int(round(temperature)))
    report += "\"barometer\": \"%s\", " %(int(round(barometer)))
    report += "\"humid\": \"%s\" , " %(int(round(humidity)))
    report += "\"windspeed\": \"%s\", " %(int(round(windSpeed)))
    report += "\"winddirection\": \"%s\", " %(directionString)
    report += "\"raintoday\": \"%s\", " %(rainToday)
    report += "\"westPatioLight\": \"%s\", " %(westPatioLight.lower())
    report += "\"cactusSpot\": \"%s\", " %(cactusSpot.lower())
    report += "\"outsideGarage\": \"%s\", " %(outsideGarage.lower())
    report += "\"frontPorch\": \"%s\", " %(frontPorch.lower())
    report += "\"outsideLights\": \"%s\", " %(outsideLights.lower())
    report += "\"mbLight\": \"%s\", " %(mbLight.lower())
    report += "\"gDoor1\": \"%s\", " %(gDoor1.lower())
    report += "\"gDoor2\": \"%s\", " %(gDoor2.lower())
    report += "\"nThermoMode\": \"%s\", " %(nThermoMode.lower())
    report += "\"sThermoMode\": \"%s\", " %(sThermoMode.lower())
    report += "\"nThermoTemp\": \"%s\", " %(nThermoTemp.lower())
    report += "\"sThermoTemp\": \"%s\", " %(sThermoTemp.lower())
    report += "\"nThermoPeak\": \"%s\", " %(nThermoPeak.lower())
    report += "\"sThermoPeak\": \"%s\", " %(sThermoPeak.lower())
    report += "\"nThermoModeSet\": \"%s\", " %(nThermoModeSet.lower())
    report += "\"sThermoModeSet\": \"%s\", " %(sThermoModeSet.lower())
    report += "\"nThermoFanSet\": \"%s\", " %(nThermoFanSet.lower())
    report += "\"sThermoFanSet\": \"%s\", " %(sThermoFanSet.lower())
    report += "\"nThermoTempSet\": \"%s\", " %(nThermoTempSet.lower())
    report += "\"sThermoTempSet\": \"%s\", " %(sThermoTempSet.lower())
    report += "\"lastEntry\": \"isHere\" "
    report += "} } }" 
    # Print something to show it's alive
    #print report
    #lprint("Tick")
    err = awsMqtt.publish("$aws/things/house/shadow/update",report)
    if err[0] != 0:
        lprint("got error {} on publish".format(err[0]))

# The idea is that I get a delta message from AWS IOT and then, after some
# translation, pass it off to the local mqtt server for delivery to whatever
# process will actually handle the command.
#
# Yes, you CAN connect to two mqtt servers at once.

if __name__ == "__main__":
    # these are the two aws subscriptions you need to operate with
    # the 'delta' is for changes that need to be taken care of
    # and the 'documents' is where the various states and such
    # are kept
    awsShadowDelta = "$aws/things/house/shadow/update/delta"
    awsShadowDocuments = "$aws/things/house/shadow/update/documents"
    # create an aws mqtt client and set up the connect handlers
    awsMqtt = mqtt.Client()
    awsMqtt.on_connect = on_awsConnect
    awsMqtt.on_message = on_awsMessage
    # certificates, host and port to use
    awsHost = "data.iot.us-east-1.amazonaws.com"
    awsPort = 8883
    caPath = "/home/pi/src/house/keys/aws-iot-rootCA.crt"
    certPath = "/home/pi/src/house/keys/cert.pem"
    keyPath = "/home/pi/src/house/keys/privkey.pem"
    # now set up encryption and connect
    awsMqtt.tls_set(caPath, certfile=certPath, keyfile=keyPath, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)
    awsMqtt.connect(awsHost, awsPort, keepalive=60)
    lprint ("did the connect")
    ##########################
    #
    # Now the Desert Home mqtt server that will be used
    # First, get the stuff from the houserc file
    hv = getHouseValues()
    # I just use the process name as the name to mqtt
    processName = os.path.basename(sys.argv[0])

    dhMqtt = mqtt.Client(client_id=processName, clean_session=True)
    dhMqttServer = hv["mqttserver"]
    dhMqtt.on_connect = on_dhConnect
    dhMqtt.on_message = on_dhMessage
    dhMqtt.connect(dhMqttServer, port=1883, keepalive=30)

    # the databases where I'm storing stuff
    hv = getHouseValues()
    # the weather database
    dbName = hv["weatherDatabase"]
    dbHost = hv["weatherHost"]
    dbPassword = hv["weatherPassword"]
    dbUser = hv["weatherUser"]
    # the house database
    hdbName = hv["houseDatabase"]
    hdbHost = hv["houseHost"]
    hdbPassword = hv["housePassword"]
    hdbUser = hv["houseUser"]
    
    # Now that everything is ready, start the two mqtt loops
    # I'm not I have to wait, but it feels safer
    awsMqtt.loop_start()
    # I have to loop both of them or they time out and I get an 
    # err 32 (broken pipe)
    dhMqtt.loop_start()
    lprint ("both mqtt loops started")

    # this timer fires every so often to update the
    # Amazon alexa device shaddow; check 'seconds' below
    shadowUpdateTimer = timer(updateIotShadow, seconds=10)
    lprint("Alexa Handling started")

    # The main loop
    while True:
        # Wait a bit
        checkTimer.tick()
        time.sleep(0.5)
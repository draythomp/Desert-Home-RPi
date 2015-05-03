#! /usr/bin/python
'''
This is the an implementation of monitoring and controlling the Lowe's 
Iris Smart Switchs that I use.  It will join with a switch and control them
(if they are configured correctly in .houserc).  This is because I use the 
switches to monitor power usage of various items around the house.  It 
wouldn't do to allow someone to turn off my freezer

This version has been adapted to support more than one switch and will 
add a new record to my database to hold the data.  Adapt it as you need 
to.

Have fun
'''
from xbee import ZigBee 
import logging
import datetime
import time
import serial
import sys
import shlex
import MySQLdb as mdb
import binascii
import cherrypy
from houseutils import lprint, getHouseValues, timer, checkTimer, dbTimeStamp

# this is the only way I could think of to get the address strings to store.
# I take the ord() to get a number, convert to hex, then take the 3 to end
# characters and pad them with zero and finally put the '0x' back on the front
# I put spaces in between each hex character to make it easier to read.  This
# left an extra space at the end, so I slice it off in the return statement.
# I hope this makes it easier to grab it out of the database when needed
def addrToString(funnyAddrString):
    hexified = ''
    for i in funnyAddrString:
        hexified += '0x' + hex(ord(i))[2:].zfill(2) + ' '
    return hexified[:-1]
    

# this is a call back function.  When a message
# comes in this function will get the data
def messageReceived(data):
    #print 'gotta packet' 
    #print data
    clusterId = (ord(data['cluster'][0])*256) + ord(data['cluster'][1])
    #print 'Cluster ID:', hex(clusterId),
    if (clusterId == 0x13):
        # This is the device announce message.
        # due to timing problems with the switch itself, I don't 
        # respond to this message, I save the response for later after the
        # Match Descriptor request comes in.  You'll see it down below.
        # if you want to see the data that came in with this message, just
        # uncomment the 'print data' comment up above
        print 'Device Announce Message'
    elif (clusterId == 0x8005):
        # this is the Active Endpoint Response This message tells you
        # what the device can do, but it isn't constructed correctly to match 
        # what the switch can do according to the spec.  This is another 
        # message that gets it's response after I receive the Match Descriptor
        print 'Active Endpoint Response'
    elif (clusterId == 0x0006):
        # Match Descriptor Request; this is the point where I finally
        # respond to the switch.  Several messages are sent to cause the 
        # switch to join with the controller at a network level and to cause
        # it to regard this controller as valid.
        #
        # First the Active Endpoint Request
        payload1 = '\x00\x00'
        zb.send('tx_explicit',
            dest_addr_long = data['source_addr_long'],
            dest_addr = data['source_addr'],
            src_endpoint = '\x00',
            dest_endpoint = '\x00',
            cluster = '\x00\x05',
            profile = '\x00\x00',
            data = payload1
        )
        print 'sent Active Endpoint'
        # Now the Match Descriptor Response
        payload2 = '\x00\x00\x00\x00\x01\x02'
        zb.send('tx_explicit',
            dest_addr_long = data['source_addr_long'],
            dest_addr = data['source_addr'],
            src_endpoint = '\x00',
            dest_endpoint = '\x00',
            cluster = '\x80\x06',
            profile = '\x00\x00',
            data = payload2
        )
        print 'Sent Match Descriptor'
        # Now there are two messages directed at the hardware
        # code (rather than the network code.  The switch has to 
        # receive both of these to stay joined.
        payload3 = '\x11\x01\x01'
        zb.send('tx_explicit',
            dest_addr_long = data['source_addr_long'],
            dest_addr = data['source_addr'],
            src_endpoint = '\x00',
            dest_endpoint = '\x02',
            cluster = '\x00\xf6',
            profile = '\xc2\x16',
            data = payload2
        )
        payload4 = '\x19\x01\xfa\x00\x01'
        zb.send('tx_explicit',
            dest_addr_long = data['source_addr_long'],
            dest_addr = data['source_addr'],
            src_endpoint = '\x00',
            dest_endpoint = '\x02',
            cluster = '\x00\xf0',
            profile = '\xc2\x16',
            data = payload4
        )
        print 'Sent hardware join messages'
        # now that it should have joined, I'll add a record to the database to
        # hold the status.  I'll just name the device 'unknown' so it can 
        # be updated by hand using sqlite3 directly.  If the device already exists,
        # I'll leave the name alone and just use the existing record
        # Yes, this means you'll have to go into the database and assign it a name
        # 
        dbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, 
                db=dbName)
        c = dbconn.cursor()
        try:
            # See if the device is already in the database
            # if not, add a record with the name 'unknown',
            # then go correct the name using the human interface
            # to sqlite3
            c.execute("select name from smartswitch "
                "where longaddress = %s; ",
                (addrToString(data['source_addr_long']),))
            switchrecord = c.fetchone()
            if switchrecord is not None:
                lprint ("Device %s is rejoining the network" %(switchrecord[0]))
            else:
                lprint ("Adding new device")
                c.execute("insert into smartswitch(name,longaddress, shortaddress, status, watts, twatts, utime)"
                    "values (%s, %s, %s, %s, %s, %s, %s);",
                    ('unknown',
                    addrToString(data['source_addr_long']),
                    addrToString(data['source_addr']),
                    'unknown',
                    '0',
                    '0',
                    dbTimeStamp()))
                dbconn.commit()
        except mdb.Error, e:
            lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
        dbconn.close()

    elif (clusterId == 0xef):
        clusterCmd = ord(data['rf_data'][2])
        if (clusterCmd == 0x81):
            usage = ord(data['rf_data'][3]) + (ord(data['rf_data'][4]) * 256)
            dbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, 
                db=dbName)
            c = dbconn.cursor()
            # get device name from database
            try:
                c.execute("select name from smartswitch "
                    "where longaddress = %s; ",
                    (addrToString(data['source_addr_long']),))
                name = c.fetchone()[0].capitalize()
                #lprint ("%s Instaneous Power, %d Watts" %(name, usage))
                # do database updates
                c.execute("update smartswitch "
                    "set watts =  %s, "
                    "shortaddress = %s, "
                    "utime = %s where longaddress = %s; ",
                    (usage, addrToString(data['source_addr']), 
                        dbTimeStamp(), addrToString(data['source_addr_long'])))
                dbconn.commit()
            except mdb.Error, e:
                lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
            dbconn.close()
        elif (clusterCmd == 0x82):
            usage = (ord(data['rf_data'][3]) +
                (ord(data['rf_data'][4]) * 256) +
                (ord(data['rf_data'][5]) * 256 * 256) +
                (ord(data['rf_data'][6]) * 256 * 256 * 256) )
            upTime = (ord(data['rf_data'][7]) +
                (ord(data['rf_data'][8]) * 256) +
                (ord(data['rf_data'][9]) * 256 * 256) +
                (ord(data['rf_data'][10]) * 256 * 256 * 256) )
            dbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, 
                db=dbName)
            c = dbconn.cursor()
            c.execute("select name from smartswitch "
                "where longaddress = %s; ",
                (addrToString(data['source_addr_long']),))
            name = c.fetchone()[0].capitalize()
            lprint ("%s Minute Stats: Usage, %d Watt Hours; Uptime, %d Seconds" %(name, usage/3600, upTime))
            # update database stuff
            try:
                c.execute("update smartswitch "
                    "set twatts =  %s, "
                    "shortaddress = %s, "
                    "utime = %s where longaddress = %s; ",
                    (usage, addrToString(data['source_addr']), 
                        dbTimeStamp(), addrToString(data['source_addr_long'])))
                dbconn.commit()
            except mdb.Error, e:
                lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
            dbconn.close()
            
    elif (clusterId == 0xf0):
        clusterCmd = ord(data['rf_data'][2])
        # print "Cluster Cmd:", hex(clusterCmd),
        # if (clusterCmd == 0xfb):
            #print "Temperature ??"
        # else:
            #print "Unimplemented"
    elif (clusterId == 0xf6):
        clusterCmd = ord(data['rf_data'][2])
        # if (clusterCmd == 0xfd):
            # pass #print "RSSI value:", ord(data['rf_data'][3])
        # elif (clusterCmd == 0xfe):
            # pass #print "Version Information"
        # else:
            # pass #print data['rf_data']
    elif (clusterId == 0xee):
        clusterCmd = ord(data['rf_data'][2])
        status = ''
        if (clusterCmd == 0x80):
            if (ord(data['rf_data'][3]) & 0x01):
                status = "ON"
            else:
                status = "OFF"
            dbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, 
                db=dbName)
            c = dbconn.cursor()
            c.execute("select name from smartswitch "
                "where longaddress = %s; ",
                (addrToString(data['source_addr_long']),))
            print c.fetchone()[0].capitalize(),
            print "Switch is", status
            try:
                c.execute("update smartswitch "
                    "set status =  %s, "
                    "shortaddress = %s, "
                    "utime = %s where longaddress = %s; ",
                    (status, addrToString(data['source_addr']), 
                        dbTimeStamp(), addrToString(data['source_addr_long'])))
                dbconn.commit()
            except mdb.Error, e:
                lprint ("Database Error %d: %s" % (e.args[0],e.args[1]))
            dbconn.close()
    else:
        lprint ("Unimplemented Cluster ID", hex(clusterId))
        print
'''
Someday, I may want to control these switches, so I have this code
to do it with.
'''
def sendSwitch(whereLong, whereShort, srcEndpoint, destEndpoint, 
                clusterId, profileId, clusterCmd, databytes):
    
    payload = '\x11\x00' + clusterCmd + databytes
    #print 'payload',
    #for c in payload:
    #    print hex(ord(c)),
    #print
    #print 'long address:',
    #for c in whereLong:
    #    print hex(ord(c)),
    #print
    #return    
    zb.send('tx_explicit',
        dest_addr_long = whereLong,
        dest_addr = whereShort,
        src_endpoint = srcEndpoint,
        dest_endpoint = destEndpoint,
        cluster = clusterId,
        profile = profileId,
        data = payload
        )
        
def getSwitchStatus(whichOne):
    # This command causes a message return holding the state of the switch
    print 'Switch Status for ', whichOne
    print type(whichOne)
    #print "lAddress is ", " ".join(hex(ord(n)) for n in sSwitches[whichOne]["lAddress"])
    dbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, db=dbName)
    c = dbconn.cursor()
    c.execute("select status from smartswitch where name = %s;", (whichOne,))
    result = c.fetchone()[0]
    dbconn.close()
    return result

def switchToggle(whichOne):
    if (getSwitchStatus(whichOne).lower() == "on"):
        switchOff(whichOne)
    else:
        switchOn(whichOne)
        
def switchOn(whichOne):
    print "Turning ON", whichOne;
    try:
        if (hv["iriscontrol"][whichOne] == "switchable"):
            databytes1 = '\x01'
            databytesOff = '\x01\x01'
            sendSwitch(sSwitches[whichOne]["lAddress"], sSwitches[whichOne]["sAddress"],
                '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x01', databytes1)
            sendSwitch(sSwitches[whichOne]["lAddress"], sSwitches[whichOne]["sAddress"], 
                '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x02', databytesOff)
        else:
            lprint(whichOne + "cannot be switched")
    except KeyError:
        print "couldn't find an entry in .houserc for", whichOne

            
def switchOff(whichOne):
    print "Turning Off", whichOne;
    try:
        if (hv["iriscontrol"][whichOne] == "switchable"):
            databytes1 = '\x01'
            databytesOff = '\x00\x01'
            sendSwitch(sSwitches[whichOne]["lAddress"], sSwitches[whichOne]["sAddress"],
            '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x01', databytes1)
            sendSwitch(sSwitches[whichOne]["lAddress"], sSwitches[whichOne]["sAddress"], 
            '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x02', databytesOff)
        else:
            lprint(whichOne + "cannot be switched")
    except KeyError:
        print "couldn't find an entry in .houserc for", whichOne
        
# This will become a dictionary of the switches found in the database
# each entry is keyed by its name and holds holds its long
# and short address
    
def createSwitchList():
    global sSwitches
    
    dbconn = mdb.connect(host=dbHost, user=dbUser, passwd=dbPassword, db=dbName)
    c = dbconn.cursor()
    c.execute("select * from smartswitch;")
    result = c.fetchall()
    dbconn.close()

    sSwitches = {}
    print ("")
    for item in result:
        #print item
        #print repr(item[0]), repr(item[1])
        #print("")
        # I have to unravel the way the address is stored in the database
        sSwitches.update({item[0]:{'lAddress':
            binascii.unhexlify(item[1].replace(' ','').replace('0x','')),
            'sAddress':
            binascii.unhexlify(item[2].replace(' ','').replace('0x',''))
            }})
    # Now that I have a dictionary holding the name, long and short
    # addresses for each switch, I can use it to talk to the switches


# This just puts a time stamp in the log file for tracking
def timeInLog():
    lprint("Just recording that I'm alive")

class IrisSC(object):
    @cherrypy.expose
    @cherrypy.tools.json_out() # This allows a dictionary input to go out as JSON
    def status(self):
        status = []
        for key in sSwitches:
            status.append({key:getSwitchStatus(key)})
        return status
        
    @cherrypy.expose
    def index(self):
        status = "<strong>Current Iris Switch Status</strong><br /><br />"
        for key in sSwitches:
            status += key + "&nbsp;&nbsp;" + getSwitchStatus(key) + "&nbsp;&nbsp;"
            status += '<a href="command?whichone='+ key +'&what=On"><button>On</button></a>'
            status += '<a href="command?whichone='+ key +'&what=Off"><button>Off</button></a>'
            status += '<a href="command?whichone='+ key +'&what=Toggle"><button>Toggle</button></a>'
            status += "<br />"
        return status
        
    @cherrypy.expose
    def command(self, whichone, what):
        # first change the light state
        # toggle(whichone)
        # now reload the index page to tell the user
        print "incoming with ", whichone, what
        if ( what.lower() == 'on'):
            switchOn(whichone)
        if (what.lower() == "off"):
            switchOff(whichone)
        if (what.lower() == "toggle"):
            switchToggle(whichone)
        raise cherrypy.InternalRedirect('/index')
        
def stopXBee():
    print("XBee stop handler")
    zb.halt()
    ser.close()
    
    
####################### Actually Starts Here ################################    

#-------------------------------------------------  
# get the values out of the houserc file
hv = getHouseValues()

# This is where I'll store information about the switches
sSwitches = {}

#-------------------------------------------------
# the database where I'm storing stuff
hv=getHouseValues()
dbName = hv["houseDatabase"]
dbHost = hv["houseHost"]
dbPassword = hv["housePassword"]
dbUser = hv["houseUser"]

#------------ XBee Stuff -------------------------
# this is the /dev/serial/by-id device for the USB card that holds the XBee
ZIGBEEPORT = hv["zigbeeport"]
ZIGBEEBAUD_RATE = 9600
# Open serial port for use by the XBee
ser = serial.Serial(ZIGBEEPORT, ZIGBEEBAUD_RATE)
# The XBee addresses I'm dealing with
BROADCAST = '\x00\x00\x00\x00\x00\x00\xff\xff'
UNKNOWN = '\xff\xfe' # This is the 'I don't know' 16 bit address

# Get the ip address and port number you want to use
# from the houserc file
ipAddress=hv["iriscontrol"]["ipAddress"]
port = hv["iriscontrol"]["port"]

#-------------------------------------------------
logging.basicConfig()


# now to get the list of switches out of the database so I can use them
createSwitchList()
# I'm showing the switch list for debugging and logging purposes
lprint("Switches found in database")
for key in sSwitches:
    lprint (key)
    lprint ('  long address ', repr(sSwitches[key]['lAddress']))
    lprint ('  short address ', repr(sSwitches[key]['sAddress']))
 
#------------------If you want to schedule something to happen -----
keepAliveTimer = timer(timeInLog, minutes=15)

#-----------------------------------------------------------------

# Create XBee library API object, which spawns a new thread
zb = ZigBee(ser, callback=messageReceived)

lprint ("started")
# Now configure the cherrypy server using the values grabbed from .houserc
cherrypy.config.update({'server.socket_host' : ipAddress.encode('ascii','ignore'),
                        'server.socket_port': port,
                        'engine.autoreload.on': False,
                        })
# Subscribe to the 'main' channel in cherrypy with my timer
cherrypy.engine.subscribe("main", checkTimer.tick)
# and this will kill the separate XBee receive thread 
cherrypy.engine.subscribe('stop', stopXBee)
lprint ("Hanging on the wait for HTTP message")
# Now just hang on the HTTP server looking for something to 
# come in.  The cherrypy dispatcher will update the things that
# are subscribed which will update the timers
cherrypy.quickstart(IrisSC())

lprint ("After the http wait")

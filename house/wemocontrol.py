#! /usr/bin/python
# Checking Wemo Switches
#
import subprocess
import commands
from datetime import datetime, timedelta
import time
import urllib2
import BaseHTTPServer
from socket import *
import sys
import json
import re
import argparse
import sqlite3
import cherrypy
from houseutils import lprint, getHouseValues, timer, checkTimer, dbTime

#--------This is for the HTML interface 
def openSite(Url):
    #lprint (Url)
    webHandle = None
    try:
        webHandle = urllib2.urlopen(Url, timeout=2) # give up in 2 seconds
    except urllib2.HTTPError, e:
        errorDesc = BaseHTTPServer.BaseHTTPRequestHandler.responses[e.code][0]
        #print "Error: (opensite) cannot retrieve URL: " + str(e.code) + ": " + errorDesc
        raise
    except urllib2.URLError, e:
        #print "Error: (openSite) cannot retrieve URL: " + e.reason[1]
        raise
    except:  #I kept getting strange errors when I was first testing it
        e = sys.exc_info()[0]
        #print ("(opensite) Odd Error: %s" % e )
        raise
    return webHandle

def talkHTML(ip, command):
    website = openSite("HTTP://" + ip + '/' + urllib2.quote(command, safe="%/:=&?~#+!$,;'@()*[]"))
    # now (maybe) read the status that came back from it
    if website is not None:
        websiteHtml = website.read()
        return  websiteHtml
        
# and this is for the SOAP interface        
# Extract the contents of a single XML tag from the data
def extractSingleTag(data,tag):
    startTag = "<%s" % tag
    endTag = "</%s>" % tag

    try:
        tmp = data.split(startTag)[1]
        index = tmp.find('>')
        if index != -1:
            index += 1
            return tmp[index:].split(endTag)[0].strip()
    except:
        pass
    return None

def sendSoap(actionName, whichOne, actionArguments):
    argList = ''
    soapEnd = re.compile('<\/.*:envelope>')
    if not actionArguments:
        actionArguments = {}
    for item in switches:
        if item["name"] == whichOne:
            thisOne = item
            break;
    switchIp = item["ip"]
    switchPort = item["port"]
    
    for arg,(val,dt) in actionArguments.iteritems():
        argList += '<%s>%s</%s>' % (arg,val,arg)

    soapRequest = 'POST /upnp/control/basicevent1 HTTP/1.1\r\n'
    # This is the SOAP request shell, I stuff values in it to handle
    # the various actions 
    # First the body since I need the length for the headers
    soapBody =  '<?xml version="1.0"?>\n'\
            '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\n'\
            '<SOAP-ENV:Body>\n'\
            '\t<m:%s xmlns:m="urn:Belkin:service:basicevent:1">\n'\
            '%s\n'\
            '\t</m:%s>\n'\
            '</SOAP-ENV:Body>\n'\
            '</SOAP-ENV:Envelope>' % (actionName,argList,actionName)

    #These are the headers to send with the request
    headers =   {
            'Host':'%s:%s' % (switchIp, switchPort),
            'Content-Length':len(soapBody),
            'Content-Type':'text/xml',
            'SOAPAction':'"urn:Belkin:service:basicevent:1#%s"' % (actionName)
            }
    #Generate the final payload
    for head,value in headers.iteritems():
        soapRequest += '%s: %s\r\n' % (head,value)
    soapRequest += '\r\n%s' % soapBody
    if showXml:
        print stars
        print "***REQUEST"
        print soapRequest
 
    try:
        sock = socket(AF_INET,SOCK_STREAM)
        sock.connect((switchIp,int(switchPort)))
        sock.settimeout(3);  # don't want to hang forever, ever
        sock.send(soapRequest)
        soapResponse = ""
        while True:
            data = sock.recv(1024)
            if not data:
                break
            else:
                soapResponse += data
                if soapEnd.search(soapResponse.lower()) != None:
                    break
        if showXml:
            print "***RESPONSE"
            print soapResponse
            print stars
            print ''
        sock.close()
        (header,body) = soapResponse.split('\r\n\r\n',1)
        if not header.upper().startswith('HTTP/1.') and ' 200 ' in header.split('\r\n')[0]:
            print 'SOAP request failed with error code:',header.split('\r\n')[0].split(' ',1)[1]
            errorMsg = self.extractSingleTag(body,'errorDescription')
            if errorMsg:
                print 'SOAP error message:',errorMsg
            return None
        else:
            return body
    except Exception, e:
        lprint ('Caught exception in sending:', e, switchIp, switchPort)
        sock.close()
        return None
    except KeyboardInterrupt:
        print "Keyboard Interrupt"
        sock.close()
        return None

# This will look at the result from sendSoap, and if the
# switch disappeared, it will try and get the new port number
# and update the various items.  This should allow the code 
# to continue as if the switch never decided to change its
# port number
def sendCommand(actionName, whichOne, actionArguments):
    result = sendSoap(actionName, whichOne, actionArguments)
    if result is not None:
        return result
    # it failed, now we have to do something about it
    # first, get the switch entry to check for a port change
    for item in switches:
        if item["name"] == whichOne:
            thisOne = item
            break;
    switchIp = item["ip"]
    switchPort = item["port"]
    # try to get the port number from the switch a few times
    for i in range(0,3): # Only try this three times
        lprint ("Trying to recover the switch %s"%whichOne)
        # getPort doesn't use sendSoap, so this call won't recurs
        newEntry = getPort(switchIp)
        # if the port changed, try and get the new one
        if newEntry is not None:
            # fine, it's at least alive, grab the port number,
            # print something, and and stuff it in the database
            # if it didn't change this won't break it, but if 
            # it did change, this will fix it.
            item["port"] = newEntry["port"]
            lprint ("Switch", whichOne, "changed ip from", switchPort, "to", newEntry["port"])
            dbconn = sqlite3.connect(DATABASE)
            c = dbconn.cursor()
            try:
                c.execute("update lights " 
                    "set port=? where name = ?;",
                    (newEntry["port"], whichOne))
            except sqlite3.OperationalError:
                lprint("Database is locked, record skipped")
            dbconn.commit()
            dbconn.close()
            # now try the command again
            # if it died completely it may have come back by now,
            # or if the port changed, this will try it one more time
            # it needs a limit this because this call will recurs
            result = sendSoap(actionName, whichOne, actionArguments)
            if result is not None:
                lprint("Switch recovered")
                return result
            time.sleep(1) #give the switch time to catch its breath
        else: 
            # this means the switch is not responding to HTML
            # so try the getPort again to see if it's back yet
            # There's no point in sending the soap command yet
            time.sleep(1) #give the switch time to catch its breath
            continue
    # it failed three times, just give up, die and let the system
    # restart the process.
    exit("The switch %s went away"% whichOne)
        
        
# Step through each light and see get its current state
# then record the state in the database.
def doLights():
    for switch in switches:
        thisOne = switch['name']
        updateDatabase(thisOne,get(thisOne))

def keepAlive():
    '''
    I update the database periodically with the time so I can check to see 
    if things are holding together.  I currently use the time in the light 
    switch records for this.
    '''
    lprint(" keep alive")
    for switch in switches:
        thisOne = switch['name']
        updateDatabase(thisOne, get(thisOne), force=True)

        
def get(whichone):
    ''' 
    Returns On or Off
    '''
    resp = sendCommand('GetBinaryState', whichone, {})
    if resp is not None:
        tagValue = extractSingleTag(resp, 'BinaryState').split('|')[0]
        return 'Off' if tagValue == '0' else 'On'
    return 'Off'

def on(whichone):
    """
    BinaryState is set to 'Error' in the case that it was already on.
    """
    resp = sendCommand('SetBinaryState', whichone, {'BinaryState': (1, 'Boolean')})
    if resp is not None:
        tagValue = extractSingleTag(resp, 'BinaryState').split('|')[0]
        status = 'On' if tagValue in ['1', '8', 'Error'] else 'Off'
        handleUpdate(whichone, status)
        lprint("turned %s on"%(whichone))
        return status
    return 'Off'

def off(whichone):
    """
    BinaryState is set to 'Error' in the case that it was already off.
    """
    resp = sendCommand('SetBinaryState', whichone, {'BinaryState': (0, 'Boolean')})
    if resp is not None:
        tagValue = extractSingleTag(resp, 'BinaryState').split('|')[0]
        status = 'Off' if tagValue in ['0', 'Error'] else 'On'
        handleUpdate(whichone, status)
        lprint("turned %s off"%(whichone))
        return status
    return 'Off'
    
def toggle(whichOne):
    if (get(whichOne) == 'On'):
        off(whichOne)
    else:
        on(whichOne)
        
def outsideLightsOn():
    lprint (" Outside lights on")
    on("outsidegarage")
    on("frontporch")
    on("cactusspot")
    
def outsideLightsOff():
    lprint (" Outside lights off")
    off("outsidegarage")
    off("frontporch")
    off("cactusspot")

        
def handleUpdate(whichone, status):
    for i in switches:
        if i['name'] == whichone:
            i['status'] = status
    updateDatabase(whichone, status)
    
def updateDatabase(whichone, status, force=False):
    ''' 
    This is running on a Pi and is not event driven, so polling like
    this will result in considerable wear to the SD card.  So, I'm going to 
    read the database to see if it needs to be changed before I change it.  
    According to everything I've read, reads are free, it's the writes that
    eat up the card.
    '''
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    c.execute("select status from lights where name = ?;",
        (whichone,))
    oldstatus = c.fetchone()
    if oldstatus[0] != status or force == True:
        lprint ("Had to update database %s, %s"%(whichone, status))
        try:
            c.execute("update lights " 
                "set status = ?, utime = ? where name = ?;",
                (status, dbTime(), whichone))
            dbconn.commit()
        except sqlite3.OperationalError:
            lprint("Database is locked, record skipped")
    dbconn.close()

# If a command comes in from somewhere, this is where it's handled.
def handleCommand(command):
    lprint(str(command))
    # the command comes in from php as something like
    # ('s:17:"AcidPump, pumpOff";', 2)
    # so command[0] is 's:17:"AcidPump, pumpOff'
    # then split it at the "  and take the second item
    try:
        c = str(command[0].split('\"')[1]).split(',')
    except IndexError:
        c = str(command[0]).split(' ')    #this is for something I sent from another process
    lprint(c)
    if (c[0] == 'OutsideLightsOn'):
        outsideLightsOn()
    elif (c[0] == 'OutsideLightsOff'):
        outsideLightsOff()
    elif (c[0] == 'fPorchToggle'):
        toggle("frontporch")
    elif(c[0] == 'garageToggle'):
        toggle("outsidegarage")
    elif (c[0] == 'cactusToggle'):
        toggle("cactusspot")
    elif (c[0] == 'patioToggle'):
        toggle("patio")
    else:
        lprint("Weird command = " + str(c))

# First the process interface, it consists of a status report and
# a command receiver.
class WemoSC(object):
    @cherrypy.expose
    @cherrypy.tools.json_out() # This allows a dictionary input to go out as JSON
    def status(self):
        status = []
        for item in switches:
            status.append({item["name"]:get(item["name"])})
        return status
        
    @cherrypy.expose
    def pCommand(self, command):
        handleCommand((command,0));
        
    @cherrypy.expose
    def index(self):
        status = "<strong>Current Wemo Light Switch Status</strong><br /><br />"
        for item in switches:
            status += item["name"] +" is " + get(item["name"]) + "&nbsp;&nbsp;"
            status += '<a href="wemocommand?whichone='+item["name"]+'"><button>Toggle</button></a>'
            status += "<br />"
        return status
        
    @cherrypy.expose
    def wemocommand(self, whichone):
        # first change the light state
        toggle(whichone)
        # now reload the index page to tell the user
        raise cherrypy.InternalRedirect('/index')

# given the ip of a Belkin device this will try the ports that
# are used on the Wemo switches to see which one works.  The assumption
# is that if none of the ports work, it's not a switch, it's a modem or
# something else.
def getPort(ip):
    entry = []
    for p in ["49153", "49154", "49155"]:
        try:
            resp = talkHTML(ip + ':' + p + "/setup.xml", "")
            if debug:
                print "\tfound one at", b[0], "port", p
            if showXml:
                print stars
                print "response from switch"
                print resp
                print stars
            name = extractSingleTag(resp, 'friendlyName')
            model = extractSingleTag(resp, 'modelName')
            entry = {"mac":b[1],"ip":b[0], "port":p, "name":name, "model":model}
            return entry
        except timeout:
            continue
        except urllib2.URLError:
            continue
        except:
            e = sys.exc_info()[0]
            print ("Unexpected Error: %s" % e )
            continue
    return None
        
####################### Actually Starts Here ################################    
debug = False
showXml = False
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug",
        action = "store_true",
        help='debug flag')
    parser.add_argument("-x", "--xml",
        action = "store_true",
        help='show xml')
    parser.add_argument('count',type=int);
    args = parser.parse_args()
    if args.debug:
        print "Running with debug on"
        debug = True
    if args.xml:
        print "Running with showXML on"
        showXml = True
    targetNumber = args.count

    stars = "*********************************************"

    #-------------------------------------------------
    # the database where I'm storing stuff
    DATABASE=getHouseValues()["database"]
    lprint("Using database ", DATABASE);
    # Get the ip address and port number you want to use
    # from the houserc file
    ipAddress=getHouseValues()["wemocontrol"]["ipAddress"]
    port = getHouseValues()["wemocontrol"]["port"]
    lprint("started looking for {} switches".format(targetNumber))

    # This works on my machine, but you may have to mess with it
    # The arp-scan below tells it not to look up the manufacturer because I
    # didn't want to worry about keeping the tables that are used up to date,
    # the -l tells it to find the local net address on its own, and 
    # -v (verbose) will print that net address so I can show it for debugging
    # I take the scan range out of the .houserc file, it's an entry under wemocontrol
    # that looks like "scanRange":"192.168.0.1-192.168.0.50" adjust this as
    # needed
    try:
        scanRange = getHouseValues()["wemocontrol"]["scanRange"]
        arpCommand = "arp-scan -q -v %s 2>&1" %(scanRange)
    except KeyError:
        print "No entry in .houserc for wemocontrol scanRange"
        exit();

    while True:
        devices = [];
        # first the devices on the network
        if debug:
            print "arp-scan command is:", arpCommand
        theList = subprocess.check_output(arpCommand,shell=True);
        # split the output of the arp-scan into lines instead of a single string
        lines = theList.splitlines()
        # this looks at each line and grabs the addresses we're interested in
        # while ignoring the lines that are just information.
        for line in lines:
            allowedDigits = set("0123456789abcdef:. \t")
            if all(c in allowedDigits for c in line):
                d = line.split()
                try:
                    devices.append([d[0], d[1]])
                except IndexError: # an empty line will pass the test
                    continue
        # arp-scan can give the same addresses back more than once
        # step through the list and remove duplicates
        temp = []
        for e in devices:
            if e not in temp:
                temp.append(e)
        devices = temp
        if debug:
            print devices
        # for each device, look up the manufacturer to see if it was registered
        # to belkin
        bDevices = []
        # I got this list direct from the IEEE database and it may
        # need to be updated in a year or two.
        belkinList = ("001150", "00173F", "001CDF", "002275", "0030BD", 
                        "08863B", "94103E", "944452", "B4750E", "C05627", "EC1A59")
        for d in devices:
            if d[1].replace(':','')[0:6].upper() in belkinList:
                    bDevices.append([d[0],d[1]])
        if debug:
            print "These are the Belkin devices on the network"
            print bDevices
        if len(bDevices) < targetNumber: 
            lprint ("Only found", len(bDevices), "Belkin devices, retrying")
            time.sleep(1)
            continue
        # Got all that were asked for, continue to the next step
        
        # Now that we have a list of the Belkin devices on the network
        # We have to examine them to be sure they are actually switches
        # and not a modem or something else.  This will also assure that 
        # they will actually respond to a request.  They still may not work,
        # but at least we have a chance.
        switches = []
        for b in bDevices:
            result = getPort(b[0])
            if result is not None:
                switches.append(result)
        # Did we find enough switches ?
        if len(switches) < targetNumber: 
            lprint ("Only found", len(switches), "of them, retrying")
            devices = []
            continue
        # Yes we did, break out.
        break;
    # Now I'm going to check the database to see if it has been
    # adjusted to hold all the items (older version didn't have
    # ip, port, and mac addresses
    dbconn = sqlite3.connect(DATABASE)
    c = dbconn.cursor()
    c.execute("pragma table_info(lights);")
    dbrow = c.fetchall()
    if not any('ip' and 'mac' and 'port' in r for r in dbrow):
        lprint ("Database needs to be adjusted")
        lprint ("to hold ip, port, and MAC")
        try:
            print "adding ip if needed"
            c.execute("alter table lights add column ip text;")
        except sqlite3.OperationalError:
            print "ip was already there"
        try:
            print "adding mac if needed"
            c.execute("alter table lights add column mac text;")
        except sqlite3.OperationalError:
            print "mac was already there"
        try:
            print "adding port if needed"
            c.execute("alter table lights add column port text;")
        except sqlite3.OperationalError:
            print "port was already there"
        dbconn.commit()
    else:
        lprint ("Database already adjusted")
    for item in switches:
        try:
            c.execute("update lights " 
                "set ip = ?, mac=?, port=?where name = ?;",
                (item["ip"], item["mac"], item["port"], item["name"]))
            dbconn.commit()
        except sqlite3.OperationalError:
            lprint("Database is locked, record skipped")
    dbconn.commit()
    dbconn.close()
    lprint ("")
    lprint ("The list of", len(switches), "switches found is")
    for item in switches:
        lprint ("Friendly name:", item["name"])
        lprint ("Model:", item["model"])
        lprint ("IP address:", item["ip"])
        lprint ("Port number:", item["port"])
        lprint ("MAC:", item["mac"])
        lprint ('')
        
    # timed things.
    checkLightsTimer = timer(doLights, seconds=2)
    keepAliveTimer = timer(keepAlive, minutes=4)
    # Now configure the cherrypy server using the values
    cherrypy.config.update({'server.socket_host' : ipAddress.encode('ascii','ignore'),
                            'server.socket_port': port,
                            'engine.autoreload.on': False,
                            })
    # Subscribe to the 'main' channel in cherrypy with my timer
    cherrypy.engine.subscribe("main", checkTimer.tick)
    lprint ("Hanging on the wait for HTTP message")
    # Now just hang on the HTTP server looking for something to 
    # come in.  The cherrypy dispatcher will update the things that
    # are subscribed which will update the timers so the light
    # status gets recorded.
    cherrypy.quickstart(WemoSC())
    
    sys.exit("Told to shut down");

#! /usr/bin/python
from miranda import upnp 
from miranda import msearch
from miranda import set
import sys
import datetime
from datetime import timedelta
from datetime import datetime
import time
import sysv_ipc
import logging
import sqlite3
from houseutils import lprint, getHouseValues, timer, checkTimer
import pdb #yes, I had trouble and had to use this !!

def _send(action, whichone, args):
    if not args:
        args = {}
    entry = (item for item in lightSwitches if item["name"] == whichone).next()
    index =entry['index']
    host_info = conn.ENUM_HOSTS[index]
    device_name = 'lightswitch'
    service_name = 'basicevent'
    controlURL = host_info['proto'] + host_info['name']
    controlURL2 = host_info['deviceList'][device_name]['services'][service_name]['controlURL']
    if not controlURL.endswith('/') and not controlURL2.startswith('/'):
        controlURL += '/'
    controlURL += controlURL2

    resp = conn.sendSOAP(
        host_info['name'],
        'urn:Belkin:service:basicevent:1',
        controlURL,
        action,
        args
    )
    # Temporary fix for possible cranky switch
    if (resp == False):
        sys.exit('Crap, the switch went away')
    return resp
    
def get(whichone):
    ''' 
    Returns On or Off
    '''
    resp = _send('GetBinaryState', whichone, {})
    tagValue = conn.extractSingleTag(resp, 'BinaryState')
    return 'On' if tagValue == '1' else 'Off'

def handleUpdate(whichone, status):
    for i in lightSwitches:
        if i['name'] == whichone:
            i['status'] = status
    updateDatabase(whichone, status)

def on(whichone):
    """
    BinaryState is set to 'Error' in the case that it was already on.
    """
    resp = _send('SetBinaryState', whichone, {'BinaryState': (1, 'Boolean')})
    tagValue = conn.extractSingleTag(resp, 'BinaryState')
    status = 'On' if tagValue in ['1', 'Error'] else 'Off'
    handleUpdate(whichone, status)
    lprint("turned %s on"%(whichone))
    return status

def off(whichone):
    """
    BinaryState is set to 'Error' in the case that it was already off.
    """
    resp = _send('SetBinaryState', whichone, {'BinaryState': (0, 'Boolean')})
    tagValue = conn.extractSingleTag(resp, 'BinaryState')
    status = 'Off' if tagValue in ['0', 'Error'] else 'On'
    handleUpdate(whichone, status)
    lprint("turned %s off"%(whichone))
    return status
    
# Step through each light and see get its current state
# then record the state in the database.
def doLights():
    for switch in lightSwitches:
        thisOne = switch['name']
        updateDatabase(thisOne,get(thisOne))
        
# Look for incoming messages fromthe SysV interprocess communcation
# facility.  This is limited in that it can only talk to processes
# inside the same machine.  Inter machine comm doesn't happen
def doComm():
    global firstTime
    #global scheditem
    
    try:
        if (firstTime):
            while(True):
                try:
                    # commands could have piled up while this was 
                    # not running.  Clear them out.
                    junk = Cqueue.receive(block=False, type=0)
                    print "purging leftover commands", str(junk)
                except sysv_ipc.BusyError:
                    break
            firstTime=False
        while(True):
            newCommand = Cqueue.receive(block=False, type=0)
            # type=0 above means suck every message off the
            # queue.  If I used a number above that, I'd
            # have to worry about the type in other ways.
            # note, I'm reserving type 1 messages for 
            # test messages I may send from time to 
            # time.  Type 2 are messages that are
            # sent by the php code in the web interface.
            # Type 3 are from the event handler. This is just like
            # the house monitor code in that respect.
            # I haven't decided on any others yet.
            handleCommand(newCommand)
    except sysv_ipc.BusyError:
        pass # Only means there wasn't anything there 

# If a command comes in from somewhere, this is where it's handled.
def handleCommand(command):
    #lprint(" " + str(command))
    # the command comes in from php as something like
    # ('s:17:"AcidPump, pumpOff";', 2)
    # so command[0] is 's:17:"AcidPump, pumpOff'
    # then split it at the "  and take the second item
    try:
        c = str(command[0].split('\"')[1]).split(',')
    except IndexError:
        c = str(command[0]).split(' ')    #this is for something I sent from another process
    #lprint(c)
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
        lprint(" Weird command = " + str(c))

# These are the commands for composite actions.  When
# I want something that turns on two lights or something
# different from basic on/off, I put it in with these.
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

def toggle(whichOne):
    if (get(whichOne) == 'On'):
        off(whichOne)
    else:
        on(whichOne)
        
def keepAlive():
    '''
    For my own purposes, I update the database periodically with the time
    so I can check to see if things are holding together.  I currently use the
    time in the light switch records for this.
    '''
    lprint(" keep alive")
    for switch in lightSwitches:
        thisOne = switch['name']
        updateDatabase(thisOne, get(thisOne), force=True)

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
        c.execute("update lights " 
            "set status = ?, utime = ? where name = ?;",
            (status, time.strftime("%A, %B, %d at %H:%M:%S"), whichone))
        dbconn.commit()
    dbconn.close()
        
if __name__ == "__main__":
    #When looking at a log, this will tell me when it is restarted
    lprint ("started")
    #-------------------------------------------------
    # the database where I'm storing stuff
    DATABASE=getHouseValues()["database"]
    lprint("Using database ", DATABASE);

    firstTime = True
    debug = False
    if not debug:
        conn =  upnp(False,False,None,0)
        ''' 
        I don't want the search for devices to run forever 
        So, I set the timeout for miranda to some number of seconds
        to limit it.
        '''
        set(3, ["set","timeout", "10"], conn)
        ''' 
        This looks at the devices that responded and gathers more data about
        them by sending them a request to itemize their capabilities.

        Sometimes a upnp device goes nuts and responds way out of
        proportion.  You can get the same device in the tables
        many times, so set the uniq to True
        
        Also, the Wemo switches don't always respond to a discover specific to 
        them.  That means I have to do a general discover and get all the devices
        on the network.  This sucks because it slows things down, so if anyone
        overcomes this problem, let me know how.
        '''
        set(3, ["set","uniq", True], conn)
        '''
        Annoyingly, sometimes the upnp devices just don't answer.  This is partially
        because the protocol used isn't a 'reliable' protocol.  So, I put the discovery
        inside a while loop to get the 4 switches I have.  I may move this value into
        my .rc file at some point, but for now, I just want to be sure I get them all.
        '''
        while True:
            ''' This is the actual search '''
            msearch(1,[msearch],conn)
            ''' and now do the interaction '''
            for index, hostInfo in conn.ENUM_HOSTS.iteritems():
                #print "************** ", index, " of ", len(conn.ENUM_HOSTS) - 1
                ''' on my network, I have a rogue device that reports badly '''
                if hostInfo['name'].find('192.168.16.254') == 0:
                    print "Odd device, ignoring"
                    continue
                ''' if you want to see them as they come in, uncomment this '''
                #print hostInfo
                if hostInfo['dataComplete'] == False:
                    xmlHeaders, xmlData = conn.getXML(hostInfo['xmlFile'])
                    conn.getHostInfo(xmlData,xmlHeaders,index)
                    
            ''' 
            now to select only the light switches from the various devices 
            that responded 
            '''
            lightSwitches=[]
            for index, host_info in conn.ENUM_HOSTS.iteritems():
                if "deviceList" in host_info:
                    if "lightswitch" in host_info["deviceList"]:
                        name = host_info["deviceList"]["lightswitch"]["friendlyName"]
                        lightSwitches.append({"name": name, "index": index, "status" : 'unknown'})
            ''' 
            OK, now I have the list of Wemo light switches that are around the 
            house, so print it and show the state of each one 
            '''
            print "this is the list of the", len(lightSwitches), "Wemo switches found."
            for switch in lightSwitches:
                switch['status'] = get(switch['name'])
                print switch
                
            if len(lightSwitches) > 3:
                print "found them all"
                break
            else:
                print "need to try again"
    # Create the message queue where commands can be read
    # I just chose an identifier of 13 because the house monitor
    # already took the number 12.
    Cqueue = sysv_ipc.MessageQueue(13, sysv_ipc.IPC_CREAT,mode=0666)
    '''
    This is a poor man's timer for task control.  I may put this in a class
    after I've run it for a while.  The reason I did it this way is that 
    APSscheduler creates a separate thread to handle timers and I don't 
    want the contention to the database of separate threads doing things
    that way.
    
    To use it, just put another entry into the table.
    '''
    lprint (" Setting up timed items")
    checkLightsTimer = timer(doLights, seconds=2)
    keepAliverTimer = timer(keepAlive, minutes=4)
    lprint ("going into the processing loop")
    while True:
        #pdb.set_trace()
        doComm()
        # Now do a tick on the timers to allow them to run
        checkTimer.tick()
        ''' 
        doing a sleep here releases the cpu for longer than the program runs
        That way I reduce the load on the machine so it can do more stuff
        '''
        time.sleep(0.25) 
        pass # this was a placeholder while writing the code.
    
    sys.exit("Should never, ever get here");


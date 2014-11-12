#! /usr/bin/python
# This is the an implementation of controlling the Lowe's Iris Smart
# Switch.  It will join with a switch and allow you to control the switch
#
# Only ONE switch though.  This implementation is a direct port of the 
# work I did for an Arduino and illustrates what needs to be done for the 
# basic operation of the switch.  If you want more than one switch, you can
# adapt this code, or use the ideas in it to make your own control software.
#
# Have fun

from xbee import ZigBee 
from apscheduler.scheduler import Scheduler
import logging
import datetime
import time
import serial
import sys
import shlex


#-------------------------------------------------
# the database where I'm storing stuff
DATABASE='/home/pi/database/desert-home'

# Whichever serial port you happen to use
XBEEPORT = '/dev/ttyUSB0'
XBEEBAUD_RATE = 9600

# The XBee addresses I'm dealing with
BROADCAST = '\x00\x00\x00\x00\x00\x00\xff\xff'
UNKNOWN = '\xff\xfe' # This is the 'I don't know' 16 bit address

switchLongAddr = '12' # This is just a number so I can recognize it later.
switchShortAddr = '12' # Both of these are changed by the code below
#-------------------------------------------------
logging.basicConfig()

#------------ XBee Stuff -------------------------
# Open serial port for use by the XBee
ser = serial.Serial(XBEEPORT, XBEEBAUD_RATE)

# this is a call back function.  When a message
# comes in this function will get the data
def messageReceived(data):
#   print 'gotta packet' 
#    print data
    # This is a test program, so use global variables and
    # save the addresses so they can be used later
    global switchLongAddr
    global switchShortAddr
    switchLongAddr = data['source_addr_long'] 
    switchShortAddr = data['source_addr']
    clusterId = (ord(data['cluster'][0])*256) + ord(data['cluster'][1])
    print 'Cluster ID:', hex(clusterId),
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
            dest_addr_long = switchLongAddr,
            dest_addr = switchShortAddr,
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
            dest_addr_long = switchLongAddr,
            dest_addr = switchShortAddr,
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
            dest_addr_long = switchLongAddr,
            dest_addr = switchShortAddr,
            src_endpoint = '\x00',
            dest_endpoint = '\x02',
            cluster = '\x00\xf6',
            profile = '\xc2\x16',
            data = payload2
        )
        payload4 = '\x19\x01\xfa\x00\x01'
        zb.send('tx_explicit',
            dest_addr_long = switchLongAddr,
            dest_addr = switchShortAddr,
            src_endpoint = '\x00',
            dest_endpoint = '\x02',
            cluster = '\x00\xf0',
            profile = '\xc2\x16',
            data = payload4
        )
        print 'Sent hardware join messages'

    elif (clusterId == 0xef):
        clusterCmd = ord(data['rf_data'][2])
        if (clusterCmd == 0x81):
            print 'Instantaneous Power',
            print ord(data['rf_data'][3]) + (ord(data['rf_data'][4]) * 256)
        elif (clusterCmd == 0x82):
            print "Minute Stats:",
            print 'Usage, ',
            usage = (ord(data['rf_data'][3]) +
                (ord(data['rf_data'][4]) * 256) +
                (ord(data['rf_data'][5]) * 256 * 256) +
                (ord(data['rf_data'][6]) * 256 * 256 * 256) )
            print usage, 'Watt Seconds ',
            print 'Up Time,',
            upTime = (ord(data['rf_data'][7]) +
                (ord(data['rf_data'][8]) * 256) +
                (ord(data['rf_data'][9]) * 256 * 256) +
                (ord(data['rf_data'][10]) * 256 * 256 * 256) )
            print upTime, 'Seconds'
    elif (clusterId == 0xf0):
        clusterCmd = ord(data['rf_data'][2])
        print "Cluster Cmd:", hex(clusterCmd),
        if (clusterCmd == 0xfb):
            print "Temperature ??"
        else:
            print "Unimplemented"
    elif (clusterId == 0xf6):
        clusterCmd = ord(data['rf_data'][2])
        if (clusterCmd == 0xfd):
            print "RSSI value:", ord(data['rf_data'][3])
        elif (clusterCmd == 0xfe):
            print "Version Information"
        else:
            print data['rf_data']
    elif (clusterId == 0xee):
        clusterCmd = ord(data['rf_data'][2])
        if (clusterCmd == 0x80):
            print "Switch is:",
            if (ord(data['rf_data'][3]) & 0x01):
                print "ON"
            else:
                print "OFF"
    else:
        print "Unimplemented Cluster ID", hex(clusterId)
        print

def sendSwitch(whereLong, whereShort, srcEndpoint, destEndpoint, 
                clusterId, profileId, clusterCmd, databytes):
    
    payload = '\x11\x00' + clusterCmd + databytes
    # print 'payload',
    # for c in payload:
        # print hex(ord(c)),
    # print
    # print 'long address:',
    # for c in whereLong:
        # print hex(ord(c)),
    # print
        
    zb.send('tx_explicit',
        dest_addr_long = whereLong,
        dest_addr = whereShort,
        src_endpoint = srcEndpoint,
        dest_endpoint = destEndpoint,
        cluster = clusterId,
        profile = profileId,
        data = payload
        )
    
#------------------If you want to schedule something to happen -----
#scheditem = Scheduler()
#scheditem.start()

#scheditem.add_interval_job(something, seconds=sometime)

#-----------------------------------------------------------------

# Create XBee library API object, which spawns a new thread
zb = ZigBee(ser, callback=messageReceived)

print "started at ", time.strftime("%A, %B, %d at %H:%M:%S")
print "Enter a number from 0 through 8 to send a command"
while True:
    try:
        time.sleep(0.001)
        str1 = raw_input("")
        # Turn Switch Off
        if(str1[0] == '0'):
            print 'Turn switch off'
            databytes1 = '\x01'
            databytesOff = '\x00\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x01', databytes1)
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x02', databytesOff)
        # Turn Switch On
        if(str1[0] == '1'):
            print 'Turn switch on'
            databytes1 = '\x01'
            databytesOn = '\x01\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x01', databytes1)
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x02', databytesOn)
        # this goes down to the test routine for further hacking
        elif (str1[0] == '2'):
            #testCommand()
            print 'Not Implemented'
        # This will get the Version Data, it's a combination of data and text
        elif (str1[0] == '3'):
            print 'Version Data'
            databytes = '\x00\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xf6', '\xc2\x16', '\xfc', databytes)
        # This command causes a message return holding the state of the switch
        elif (str1[0] == '4'):
            print 'Switch Status'
            databytes = '\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xee', '\xc2\x16', '\x01', databytes)
        # restore normal mode after one of the mode changess that follow
        elif (str1[0] == '5'):
            print 'Restore Normal Mode'
            databytes = '\x00\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xf0', '\xc2\x16', '\xfa', databytes)
        # range test - periodic double blink, no control, sends RSSI, no remote control
        # remote control works
        elif (str1[0] == '6'):
            print 'Range Test'
            databytes = '\x01\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xf0', '\xc2\x16', '\xfa', databytes)
        # locked mode - switch can't be controlled locally, no periodic data
        elif (str1[0] == '7'):
            print 'Locked Mode'
            databytes = '\x02\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xf0', '\xc2\x16', '\xfa', databytes)
        # Silent mode, no periodic data, but switch is controllable locally
        elif (str1[0] == '8'):
            print 'Silent Mode'
            databytes = '\x03\x01'
            sendSwitch(switchLongAddr, switchShortAddr, '\x00', '\x02', '\x00\xf0', '\xc2\x16', '\xfa', databytes)
#       else:
#           print 'Unknown Command'
    except IndexError:
        print "empty line"
    except KeyboardInterrupt:
        print "Keyboard interrupt"
        break
    except NameError as e:
        print "NameError:",
        print e.message.split("'")[1]
    except:
        print "Unexpected error:", sys.exc_info()[0]
        break

print "After the while loop"
# halt() must be called before closing the serial
# port in order to ensure proper thread shutdown
zb.halt()
ser.close()

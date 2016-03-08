#! /usr/bin/python
# Have fun

from xbee import ZigBee 
import logging
import datetime
import time
import serial
import sys, traceback
import shlex
from struct import *
'''
Before we get started there's a piece of this that drove me nuts.  Each message to a 
Zigbee cluster has a length and a header.  The length isn't talked about at all in the 
Zigbee documentation (that I could find) and the header byte is drawn backwards to
everything I've ever dealt with.  So, I redrew the header byte so I could understand
and use it:

7   6   5   4   3   2   1   0
            X                   Disable Default Response 1 = return default message
                X               Direction 1 = server to client, 0 = client to server
                    X           Manufacturer Specific 
                            X   Frame Type 1 = cluster specific, 0 = entire profile
                                    
So, to send a cluster command, set bit zero, and to get an attribute from a cluster
set bit 4.  If you want to be sure you get a reply, set the default response.  I haven't
needed the manufacturer specific bit yet.

'''

def printData(data):
    print "********** Message Contents"
    for key, value in data.iteritems():
        if key == "id":
            print key, value
        else:
            print key, "".join("%02x " % ord(b) for b in data[key])
    print "**********"

def getAttributes(data, thisOne):
    ''' OK, now that I've listed the clusters, I'm going to see about 
    getting the attributes for one of them by sending a Discover
    attributes command.  This is not a ZDO command, it's a ZCL command.
    ZDO = ZigBee device object - the actual device
    ZCL = Zigbee device cluster - the collection of routines to control it.
        Frame control field, bit field,  first byte
            bits 0-1, frame type field
                00 entire profile
                01 specific to a particular cluster
                10-11 reserved (don't use)
                Note, if you're sending commands, this should be 01
                if you're reading attributes, it should be 00
            bit 2, manufacturer specific, if this bit is set, include
                   the manufacturer code (below)
            bit 3 direction, this determines if it is from a client to 
                   server.  
                 1 server to client
                 0 client to server
                 Note, server and client are specific to zigbee, not
                 the purpose of the machine, so think about this.  For
                 example to turn an on/off switch on, you have to be the
                 server so this bit will be 01
            bit 4 disable default response
            bits 5-7 reserved (set to zero)
        Manufacturer code,  either 2 bytes or not there 
        Transaction sequence number, byte
        Command identifier, byte
        Frame payload,  variable, the command bytes to do something
        
        frame control bits = 0b00 (this means a BINARY 00)
        manufacturer specific bit = 0, for normal, or one for manufacturer
        So, the frame control will be 0000000
        discover attributes command identifier = 0x0c
        
        then a zero to indicate the first attribute to be returned
        and a 0x0f to indicate the maximum number of attributes to 
        return.
    '''
    print "Sending Discover Attributes"
    zb.send('tx_explicit',
        dest_addr_long = data['source_addr_long'],
        dest_addr = data['source_addr'],
        src_endpoint = '\x00',
        dest_endpoint = '\x01',
        cluster = thisOne, # cluster I want to know about
        profile = '\x01\x04', # home automation profile
        # means: frame control 0, sequence number 0xaa, command 0c,
        # start at 0x0000 for a length of 0x0f
        data = '\x00' + '\xaa' + '\x0c'+ '\x00' + '\x00'+ '\x0f'
        )

# this is a call back function.  When a message
# comes in this function will get the data
def messageReceived(data):
    
    try:
        # This is the long address of my door switch device
        # since I have several other devices and they are transmitting
        # all the time, I'm excluding them and only allowing the
        # door switch in
        if data['source_addr_long'] != '\x00\x0d\x6f\x00\x03\xc2\x71\xcc':
            return
            
        print ''
        print 'gotta packet',
        #printData(data)
        if (data['id'] == 'rx_explicit'):
            print "RF Explicit"
            printData(data)
            clusterId = (ord(data['cluster'][0])*256) + ord(data['cluster'][1])
            print 'Cluster ID:', hex(clusterId),
            print "profile id:", repr(data['profile'])
            
            if (data['profile']=='\x00\x00'): # The General Profile
                if (clusterId == 0x0000):
                    print ("Network (16-bit) Address Request")
                    #printData(data)
                elif (clusterId == 0x0004):
                    # Simple Descriptor Request, 
                    print("Simple Descriptor Request")
                    #printData(data)
                elif (clusterId == 0x0005):
                    # Active Endpoint Request, 
                    print("Active Endpoint Request")
                    #printData(data)
                elif (clusterId == 0x0006):
                    print "Match Descriptor Request"
                    #printData(data)
                    print "Sending match descriptor response"
                    zb.send('tx_explicit',
                        dest_addr_long = data['source_addr_long'],
                        dest_addr = data['source_addr'],
                        src_endpoint = '\x00',
                        dest_endpoint = '\x00',
                        cluster = '\x80\x06',
                        profile = '\x00\x00',
                        options = '\x01',
                        data = '\x04\x00\x00\x00\x01\x02'
                    )
                    print "howdy, trying something"
                    time.sleep(2)
                    zb.send('tx_explicit',
                        dest_addr_long = data['source_addr_long'],
                        dest_addr = data['source_addr'],
                        src_endpoint = '\x02',
                        dest_endpoint = '\x02',
                        cluster = '\x00\xf6',
                        profile = '\xc2\x16',
                        data = '\x11\x01\x01'
                        )
                    print "next"
                    zb.send('tx_explicit',
                       dest_addr_long = data['source_addr_long'],
                       dest_addr = data['source_addr'],
                       src_endpoint = '\x00',
                       dest_endpoint = '\x02',
                       cluster = '\x00\xf0',
                       profile = '\xc2\x16',
                       data = '\x19\x01\xfa\x00\x01'
                    )
                elif (clusterId == 0x0008):
                    # I couldn't find a definition for this 
                    print("This was probably sent to the wrong profile")
                elif (clusterId == 0x0013):
                    # This is the device announce message.
                    print 'Device Announce Message'
                    # this will tell me the address of the new thing
                    # so I'm going to send an active endpoint request
                    print 'Sending active endpoint request'
                    epc = '\xaa'+data['source_addr'][1]+data['source_addr'][0]
                    print "".join("%02x " % ord(b) for b in epc)
                    zb.send('tx_explicit',
                        dest_addr_long = data['source_addr_long'],
                        dest_addr = data['source_addr'],
                        src_endpoint = '\x00',
                        dest_endpoint = '\x00',
                        cluster = '\x00\x05',
                        profile = '\x00\x00',
                        options = '\x01',
                        data = epc
                    )

                    #printData(data)
                elif (clusterId == 0x8000):
                    print("Network (16-bit) Address Response")
                    #printData(data)
                elif (clusterId == 0x8038):
                    print("Management Network Update Request");
                elif (clusterId == 0x8005):
                    # this is the Active Endpoint Response This message tells you
                    # what the device can do
                    print 'Active Endpoint Response'
                    printData(data)
                elif (clusterId == 0x8004):
                    print "simple descriptor response"
                else:
                    print ("Unimplemented Cluster ID", hex(clusterId))
                    print
            elif (data['profile']=='\xc2\x16'): # Alertme Specific
                print "Got into the Alertme profile"
                if (clusterId == 0x00f6):
                    print "Sending init message"
                    pass
                    
                elif (clusterId == 0x000f):
                    pass
                elif (clusterId == 0x00f2):
                    pass
                elif (clusterId == 0x00ef):
                    pass
                elif (clusterId == 0x00f0):
                    pass
                elif (clusterId == 0x0500):
                    pass
            else:
                print ("Unimplemented Profile ID")
        elif(data['id'] == 'route_record_indicator'):
            print("Route Record Indicator")
        else:
            print("some other type of packet")
            print(data)
    except:
        print "I didn't expect this error:", sys.exc_info()[0]
        traceback.print_exc()
        

#------------ XBee Stuff -------------------------
# this is the /dev/serial/by-id device for the USB card that holds the XBee
ZIGBEEPORT = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A901QL3F-if00-port0"
ZIGBEEBAUD_RATE = 9600
# Open serial port for use by the XBee
ser = serial.Serial(ZIGBEEPORT, ZIGBEEBAUD_RATE)


# The XBee addresses I'm dealing with
BROADCAST = '\x00\x00\x00\x00\x00\x00\xff\xff'
theSwitch = '\x00\x0d\x6f\x00\x03\x58\x05\xc2'
UNKNOWN = '\xff\xfe' # This is the 'I don't know' 16 bit address

#-------------------------------------------------
logging.basicConfig()

    
# Create XBee library API object, which spawns a new thread
zb = ZigBee(ser, callback=messageReceived)

print ("started")
notYet = True;
firstTime = True;
while True:
    try:
        time.sleep(5)
        if (firstTime):
            # this is in case I need some initialization in the
            # future
            firstTime = False
        print ("tick")
        
        sys.stdout.flush() # if you're running non interactive, do this

    except KeyboardInterrupt:
        print ("Keyboard interrupt")
        break
    except:
        print ("I didn't expect this error:", sys.exc_info()[0])
        traceback.print_exc()
        break
print ("After the while loop")
# halt() must be called before closing the serial
# port in order to ensure proper thread shutdown
zb.halt()
ser.close()

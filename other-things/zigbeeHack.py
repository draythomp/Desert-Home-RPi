#! /usr/bin/python
# This is the super secret home automation key that is needed to 
# implement the HA profile.
# KY parameter on XBee 5a6967426565416c6c69616e63653039
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
    for d in data:
        print d, ' : ',
        for e in data[d]:
            print "{0:02x}".format(ord(e)),
        if (d =='id'):
            print "({})".format(data[d]),
        print

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
        print 'gotta packet',
        #print data
        if (data['id'] == 'rx_explicit'):
            print "RF Explicit"
            #printData(data)
            clusterId = (ord(data['cluster'][0])*256) + ord(data['cluster'][1])
            print 'Cluster ID:', hex(clusterId),
            print "profile id:", repr(data['profile']),
            if (data['profile']=='\x01\x04'): # Home Automation Profile
                # This has to be handled differently than the general profile
                # each response if from a cluster that is actually doing something
                # so there are attributes and commands to think about.
                #
                # Since this is a ZCL message; which actually means this message is 
                # is supposed to use the ZigBee cluster library to actually do something
                # like turn on a light or check to see if it's on, the command way down
                # in the rf_data is important.  So, the commands may be repeated in
                # each cluster and do slightly different things
                #
                # I'm going to grab the cluster command out of the rf_data first so 
                # I don't have to code it into each cluster
                #print "take this apart"
                #print repr(data['rf_data'])
                if (data['rf_data'][0] == '\x08'): # was it successful?
                    #should have a bit check to see if manufacturer data is here
                    cCommand = data['rf_data'][2]
                    print "Cluster command: ", hex(ord(cCommand))
                else:
                    print "Cluster command failed"
                    return
                # grab the payload data to make it easier to work with
                payload = data['rf_data'][3:] #from index 3 on is the payload for the command
                datatypes={'\x00':'no data',
                            '\x10':'boolean',
                            '\x18':'8 bit bitmap',
                            '\x20':'unsigned 8 bit integer',
                            '\x21':'unsigned 24 bit integer',
                            '\x30':'8 bit enumeration',
                            '\x42':'character string'}
                print "Raw payload:",repr(payload)
                # handle these first commands in a general way
                if (cCommand == '\x0d'): # Discover Attributes
                    # This tells you all the attributes for a particular cluster
                    # and their datatypes
                    print "Discover attributes response"
                    if (payload[0] == '\x01'):
                        print "All attributes returned"
                    else:
                        print "Didn't get all the attributes on one try"
                    i = 1
                    if (len(payload) == 1): # no actual attributes returned
                        print "No attributes"
                        return
                    while (i < len(payload)-1):
                        print "    Attribute = ", hex(ord(payload[i+1])) , hex(ord(payload[i])),
                        try:
                            print datatypes[payload[i+2]]
                            i += 3
                        except:
                            print "I don't have an entry for datatype:", hex(ord(payload[i+2]))
                            return
                            
                if (clusterId == 0x0000): # Under HA this is the 'Basic' Cluster
                    pass
                elif (clusterId == 0x0003): # 'identify' should make it flash a light or something 
                    pass
                elif (clusterId == 0x0004): # 'Groups'
                    pass
                elif (clusterId == 0x0005): # 'Scenes'  
                    pass
                elif (clusterId == 0x0006): # 'On/Off' this is for switching or checking on and off  
                    print "inside cluster 6"
                
                elif (clusterId == 0x0008): # 'Level'  
                    pass
                else:
                    print("Haven't implemented this yet")
            elif (data['profile']=='\x00\x00'): # The General Profile
                if (clusterId == 0x0000):
                    print ("Network (16-bit) Address Request")
                    #printData(data)
                elif (clusterId == 0x0008):
                    # I couldn't find a definition for this 
                    print("This was probably sent to the wrong profile")
                elif (clusterId == 0x0004):
                    # Simple Descriptor Request, 
                    print("Simple Descriptor Request")
                    print("I don't respond to this")
                    #printData(data)
                elif (clusterId == 0x0013):
                    # This is the device announce message.
                    print 'Device Announce Message'
                    printData(data)
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
                    if (ord(data['rf_data'][1]) == 0): # this means success
                        print "Active Endpoint reported back is: {0:02x}".format(ord(data['rf_data'][5]))
                        
                    print("Now trying simple descriptor request on endpoint 01")
                    zb.send('tx_explicit',
                        dest_addr_long = data['source_addr_long'],
                        dest_addr = data['source_addr'],
                        src_endpoint = '\x00',
                        dest_endpoint = '\x00', # This has to go to endpoint 0 !
                        cluster = '\x00\x04', #simple descriptor request'
                        profile = '\x00\x00',
                        data = '\x13' + data['source_addr'][1] + data['source_addr'][0] + '\x01'
                    )
                elif (clusterId == 0x8004):
                    print "simple descriptor response"
                    try:
                        clustersFound = []
                        r = data['rf_data']
                        if (ord(r[1]) == 0): # means success
                            #take apart the simple descriptor returned
                            endpoint, profileId, deviceId, version, inCount = \
                                unpack('<BHHBB',r[5:12])
                            print "    endpoint reported is: {0:02x}".format(endpoint)
                            print "    profile id:  {0:04x}".format(profileId)
                            print "    device id: {0:04x}".format(deviceId)
                            print "    device version: {0:02x}".format(version)
                            print "    input cluster count: {0:02x}".format(inCount)
                            position = 12
                            # input cluster list (16 bit words)
                            for x in range (0,inCount):
                                thisOne, = unpack("<H",r[position : position+2])
                                clustersFound.append(r[position+1] + r[position])
                                position += 2
                                print "        input cluster {0:04x}".format(thisOne)
                            outCount, = unpack("<B",r[position])
                            position += 1
                            print "    output cluster count: {0:02x}".format(outCount)
                            #output cluster list (16 bit words)
                            for x in range (0,outCount):
                                thisOne, = unpack("<H",r[position : position+2])
                                clustersFound.append(r[position+1] + r[position])
                                position += 2
                                print "        output cluster {0:04x}".format(thisOne)
                            clustersFound.append('\x0b\x04')
                            print "added special cluster"
                            print "Completed Cluster List"
                    except:
                        print "error parsing Simple Descriptor"
                        printData(data)
                    print repr(clustersFound)
                    for c in clustersFound:
                        getAttributes(data, c) # Now, go get the attribute list for the cluster
                elif (clusterId == 0x0006):
                    print "Match Descriptor Request"
                    # Match Descriptor Request
                    #printData(data)
                else:
                    print ("Unimplemented Cluster ID", hex(clusterId))
                    print
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

#------------ XBee Stuff -------------------------
# this is the /dev/serial/by-id device for the USB card that holds the XBee
ZIGBEEPORT = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A600eDiR-if00-port0"
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
#           sendSwitch(whereLong=theSwitch, whereShort=UNKNOWN, srcEndpoint='\x00', 
#                   destEndpoint='\x00', clusterId='\x00\x00', profileId='\x00\x00', 
#                   clusterCmd='\x00', databytes='\x00')
            print "sending Active Endpoint Request "
            zb.send('tx_explicit',
                dest_addr_long = theSwitch,
                dest_addr = '\x94\x65',
                src_endpoint = '\x00',
                dest_endpoint = '\x00',
                cluster = '\x00\x05',
                profile = '\x00\x00',
                # The first item is a number to identify the message
                # The next two are the short address of the device
                data = '\x12' + '\x65' + '\x94'
            )
            time.sleep(10)
            print "sending 'configure reporting'"
            zb.send('tx_explicit',
                dest_addr_long = theSwitch,
                dest_addr = '\x94\x65',
                src_endpoint = '\x00',
                dest_endpoint = '\x01',
                cluster = '\x00\x06', # cluster I want to deal with
                profile = '\x01\x04', # home automation profile
                data = '\x00' + '\xaa' + '\x06' + '\x00' + '\x00' + '\x00' + '\x10' + '\x00' + '\x00' + '\x00' + '\x40' + '\x00' + '\x00'
            )

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

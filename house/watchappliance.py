#! /usr/bin/python
# This is the an implementation of monitoring the Lowe's Iris Smart
# Switch that I use.  It will join with a switch and does NOT allow you 
# to control the switch
#
# This version has been adapted to support more than one switch and will 
# add a new record to my database to hold the data.  Adapt it as you need 
# to.
#
# Have fun

from xbee import ZigBee 
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import datetime
import time
import serial
import sys
import shlex
import sqlite3
from houseutils import getHouseValues, lprint

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
	

# this is a call back function.	 When a message
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
		# what the switch can do according to the spec.	 This is another 
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
		dbconn = sqlite3.connect(DATABASE)
		c = dbconn.cursor()
		try:
			# See if the device is already in the database
			c.execute("select name from smartswitch "
				"where longaddress = ?; ",
				(addrToString(data['source_addr_long']),))
			switchrecord = c.fetchone()
			if switchrecord is not None:
				lprint ("Device %s is rejoining the network" %(switchrecord[0]))
			else:
				lprint ("Adding new device")
				c.execute("insert into smartswitch(name,longaddress, shortaddress, status, watts, twatts, utime)"
					"values (?, ?, ?, ?, ?, ?, ?);",
					('unknown',
					addrToString(data['source_addr_long']),
					addrToString(data['source_addr']),
					'unknown',
					'0',
					'0',
					time.strftime("%A, %B, %d at %H:%M:%S")))
				dbconn.commit()
		except OperationalError:
			lprint("Database is locked, record skipped")
		dbconn.close()

	elif (clusterId == 0xef):
		clusterCmd = ord(data['rf_data'][2])
		if (clusterCmd == 0x81):
			usage = ord(data['rf_data'][3]) + (ord(data['rf_data'][4]) * 256)
			dbconn = sqlite3.connect(DATABASE)
			c = dbconn.cursor()
			# This is commented out because I don't need the name
			# unless I'm debugging.
			# get device name from database
			try:
				c.execute("select name from smartswitch "
					"where longaddress = ?; ",
					(addrToString(data['source_addr_long']),))
				name = c.fetchone()[0].capitalize()
				#lprint ("%s Instaneous Power, %d Watts" %(name, usage))
				# do database updates
				c.execute("update smartswitch "
					"set watts =  ?, "
					"shortaddress = ?, "
					"utime = ? where longaddress = ?; ",
					(usage, addrToString(data['source_addr']), 
						time.strftime("%A, %B, %d at %H:%M:%S"), addrToString(data['source_addr_long'])))
				dbconn.commit()
			except OperationalError:
				lprint("Database locked, record skipped")
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
			dbconn = sqlite3.connect(DATABASE)
			c = dbconn.cursor()
			c.execute("select name from smartswitch "
				"where longaddress = ?; ",
				(addrToString(data['source_addr_long']),))
			name = c.fetchone()[0].capitalize()
			lprint ("%s Minute Stats: Usage, %d Watt Hours; Uptime, %d Seconds" %(name, usage/3600, upTime))
			# update database stuff
			try:
				c.execute("update smartswitch "
					"set twatts =  ?, "
					"shortaddress = ?, "
					"utime = ? where longaddress = ?; ",
					(usage, addrToString(data['source_addr']), 
						time.strftime("%A, %B, %d at %H:%M:%S"), addrToString(data['source_addr_long'])))
				dbconn.commit()
			except OperationalError:
				lprint("Database is locked, record skipped")
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
			dbconn = sqlite3.connect(DATABASE)
			c = dbconn.cursor()
			c.execute("select name from smartswitch "
				"where longaddress = ?; ",
				(addrToString(data['source_addr_long']),))
			print c.fetchone()[0].capitalize(),
			print "Switch is", status
			try:
				c.execute("update smartswitch "
					"set status =  ?, "
					"shortaddress = ?, "
					"utime = ? where longaddress = ?; ",
					(status, addrToString(data['source_addr']), 
						time.strftime("%A, %B, %d at %H:%M:%S"), addrToString(data['source_addr_long'])))
				dbconn.commit()
			except OperationalError:
				lprint("Database is locked, record skipped")
			dbconn.close()
	else:
		lprint ("Unimplemented Cluster ID", hex(clusterId))
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
# This just puts a time stamp in the log file for tracking
def timeInLog():
	lprint()
	
#-------------------------------------------------	
# get the values out of the houserc file
hv = getHouseValues()

#-------------------------------------------------
# the database where I'm storing stuff
DATABASE= hv["database"]

#------------ XBee Stuff -------------------------
# this is the /dev/serial/by-id device for the USB card that holds the XBee
ZIGBEEPORT = hv["zigbeeport"]
ZIGBEEBAUD_RATE = 9600
# Open serial port for use by the XBee
ser = serial.Serial(ZIGBEEPORT, ZIGBEEBAUD_RATE)


# The XBee addresses I'm dealing with
BROADCAST = '\x00\x00\x00\x00\x00\x00\xff\xff'
UNKNOWN = '\xff\xfe' # This is the 'I don't know' 16 bit address

#-------------------------------------------------
logging.basicConfig()

	
#------------------If you want to schedule something to happen -----
scheditem = BackgroundScheduler()
scheditem.start()

scheditem.add_job(timeInLog, 'interval', minutes=15)

#-----------------------------------------------------------------

# Create XBee library API object, which spawns a new thread
zb = ZigBee(ser, callback=messageReceived)

lprint ("started")
while True:
	try:
		time.sleep(0.1)
		sys.stdout.flush() # if you're running non interactive, do this

	except KeyboardInterrupt:
		lprint ("Keyboard interrupt")
		break
	except:
		lprint ("Unexpected error:", sys.exc_info()[0])
		break

lprint ("After the while loop")
# halt() must be called before closing the serial
# port in order to ensure proper thread shutdown
zb.halt()
ser.close()

#! /usr/bin/python
# This is the actual house Monitor Module
#
# I take the techniques tried in other modules and incorporate them
# to gather data around the house and save it in a data base.  The
# data base can be read for presentation in a web page and also	 
# forwarded for cloud storage and graphing. 
#
# For the XBee network, I fork off a new thread
# to do the XBee receive.  This way, the main
# code can go do something else and hand waiting
# for the XBee messages to come in to another
# process.

from xbee import ZigBee 
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import datetime
import time
import serial
import Queue
import sqlite3
import sys
import urllib2
import sysv_ipc
import shlex
from houseutils import getHouseValues, lprint

# Global items that I want to keep track of
CurrentPower = 0
DayMaxPower = 0
DayMinPower = 50000
CurrentOutTemp = 0
DayOutMaxTemp = -50
DayOutMinTemp = 200

#-------------------------------------------------
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
	except:	 #I kept getting strange errors when I was first testing it
		e = sys.exc_info()[0]
		print ("Odd Error: %s" % e )
		raise
	return webHandle
#------------------------------------------------
def controlThermo(whichOne, command):
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	c.execute("select address from thermostats "
		"where location=?; ", (whichOne,))
	thermoIp = c.fetchone()
	dbconn.close
	website = openSite("HTTP://" + thermoIp[0] + "/" + command)
	websiteHtml = website.read()
	return	websiteHtml
	
def getThermoStatus(whichOne):
	website = openSite("HTTP://" + whichOne[0] + "/status")
	# now read the status that came back from it
	websiteHtml = website.read()
	# After getting the status from the little web server on
	# the arduino thermostat, strip off the trailing cr,lf
	# and separate the values into a list that can
	# be used to tell what is going on
	return	websiteHtml.rstrip().split(",")

def ThermostatStatus():
	# The scheduler will run this as a separate thread
	# so I have to open and close the database within
	# this routine
	#print(time.strftime("%A, %B %d at %H:%M:%S"))
	# open the database and set up the cursor (I don't have a
	# clue why a cursor is needed)
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	for whichOne in ['North', 'South']:
		c.execute("select address from thermostats "
			"where location=?; ", (whichOne,))
		thermoIp = c.fetchone()
		try:
			status = getThermoStatus(thermoIp)
		except:
			break
		#print whichOne + " reports: " + str(status)
		c.execute("update thermostats set 'temp-reading' = ?, "
				"status = ?, "
				"'s-temp' = ?, "
				"'s-mode' = ?, "
				"'s-fan' = ?, "
				"peak = ?,"
				"utime = ?"
				"where location = ?;",
					(status[0],status[1],
					status[2],status[3],
					status[4],status[5],
					time.strftime("%A, %B, %d at %H:%M:%S"),
					whichOne))
		dbconn.commit()
	dbconn.close()

# this is a call back function.	 When a message
# comes in this function will get the data
def message_received(data):
	packets.put(data, block=False)
	#print 'gotta packet' 

def sendPacket(where, what):
	# I'm only going to send the absolute minimum. 
	#lprint ("sending to ", ':'.join(hex(ord(x))[2:] for x in where), what)
	zb.send('tx',
		dest_addr_long = where,
		# I always use the 'unknown' value for this
		# it's too much trouble to keep track of two
		# addresses for the device
		dest_addr = UNKNOWN,
		data = what)

# OK, another thread has caught the packet from the XBee network,
# put it on a queue, this process has taken it off the queue and 
# passed it to this routine, now we can take it apart and see
# what is going on ... whew!
def handlePacket(data):
	global CurrentPower, DayMaxPower, DayMinPower
	global CurrentOutTemp, DayOutMaxTemp, DayOutMinTemp

	#print data # for debugging so you can see things
	# this packet is returned every time you do a transmit
	# (can be configured out), to tell you that the XBee
	# actually send the darn thing
	if data['id'] == 'tx_status':
		if ord(data['deliver_status']) != 0:
			print 'Transmit error = ',
			print data['deliver_status'].encode('hex')
	# The receive packet is the workhorse, all the good stuff
	# happens with this packet.
	elif data['id'] == 'rx': 
		rxList = data['rf_data'].split(',')
		
		if rxList[0] == 'Status': #This is the status send by the old controller
			# remember, it's sent as a string by the XBees
			#print("Got Old Controller Status Packet")
			tmp = int(rxList[1]) # index 1 is current power
			if tmp > 0:	 # Things can happen to cause this
				# and I don't want to record a zero
				CurrentPower = tmp
				DayMaxPower = max(DayMaxPower,tmp)
				DayMinPower = min(DayMinPower,tmp)
				tmp = int(rxList[3]) # index 3 is outside temp
				CurrentOutTemp = tmp
				DayOutMaxTemp = max(DayOutMaxTemp, tmp)	
				DayOutMinTemp = min(DayOutMinTemp, tmp)
				dbconn = sqlite3.connect(DATABASE)
				c = dbconn.cursor()
				# do database stuff
				c.execute("update housestatus " 
					"set curentpower = ?, "
					"daymaxpower = ?,"
					"dayminpower = ?,"
					"currentouttemp = ?,"
					"dayoutmaxtemp = ?,"
					"dayoutmintemp = ?,"
					"utime = ?;",
					(CurrentPower, DayMaxPower, DayMinPower,
					CurrentOutTemp, DayOutMaxTemp,
					DayOutMinTemp,
					time.strftime("%A, %B, %d at %H:%M:%S")))
				dbconn.commit()
				dbconn.close()
		elif rxList[0] == 'AcidPump':
			# This is the Acid Pump Status packet
			# it has 'AcidPump,time_t,status,level,#times_sent_message
			# I only want to save status, level, and the last
			# time it reported in to the database for now
			#print("Got Acid Pump Packet")
			dbconn = sqlite3.connect(DATABASE)
			c = dbconn.cursor()
			c.execute("update acidpump set status = ?, "
				"'level' = ?,"
				"utime = ?;",
				(rxList[2], rxList[3],
				time.strftime("%A, %B, %d at %H:%M:%S")))
			dbconn.commit()
			dbconn.close()
		elif rxList[0] == '?\r': #incoming request for a house status message
			# Status message that is broadcast to all devices consists of:
			# power,time_t,outsidetemp,insidetemp,poolmotor	 ---more to come someday
			# all fields are ascii with poolmotor being {Low,High,Off}
			#print("Got Status Request Packet")
			dbconn = sqlite3.connect(DATABASE)
			c = dbconn.cursor()
			spower = int(float(c.execute("select rpower from power").fetchone()[0]))
			stime = int((time.time() - (7*3600)))
			sotemp = int(c.execute("select currenttemp from xbeetemp").fetchone()[0])
			sitemp = int(c.execute("select avg(\"temp-reading\") from thermostats").fetchone()[0])
			spoolm = c.execute("select motor from pool").fetchone()[0]
			dbconn.close()
			sstring = "Status,%d,%d,%d,%d,%s\r" %(spower,stime,sotemp,sitemp,spoolm)
			#print sstring.encode('ascii','ignore') #for debugging
			sendPacket(BROADCAST, sstring.encode('ascii','ignore'))
		elif rxList[0] == 'Time':
			#print("Got Time Packet")
			pass
		elif rxList[0] == 'Garage':
			#print("Got Garage Packet")
			#print(rxList)
			if len(rxList) > 2: #this means it's a status from the garage
								# not a command to the garage
				#print "updating garage in database"
				# Now stick it in the database
				dbconn = sqlite3.connect(DATABASE)
				c = dbconn.cursor()
				c.execute("update garage set door1 = ?, "
					"door2 = ?,"
					"waterh = ?,"
					"utime = ?;",
					(rxList[1], rxList[2],rxList[3].rstrip(),
					time.strftime("%A, %B, %d at %H:%M:%S")))
				dbconn.commit()
				dbconn.close()
		elif rxList[0] == 'Pool':
			#print("Got Pool Packet")
			#print(rxList)
			motor = rxList[1].split(' ')[1]
			waterfall = rxList[2].split(' ')[1]
			light = rxList[3].split(' ')[1]
			fountain = rxList[4].split(' ')[1]
			solar = rxList[5].split(' ')[1]
			ptemp = rxList[6].split(' ')[1]
			atemp = rxList[7].split(' ')[1]
			dbconn = sqlite3.connect(DATABASE)
			c = dbconn.cursor()
			c.execute("update pool set motor = ?, "
				"waterfall = ?,"
				"light = ?,"
				"fountain = ?,"
				"solar = ?,"
				"ptemp = ?,"
				"atemp = ?,"
				"utime = ?;",
				(motor, waterfall, light, fountain, 
				solar, ptemp, atemp,
				time.strftime("%A, %B, %d at %H:%M:%S")))
			dbconn.commit()
			dbconn.close()
		elif rxList[0] == 'Power':
			#print("Got Power Packet")
			#print(rxList)
			# I didn't really need to put these into variables, 
			# I could have used the strings directly, but when
			# I came back in a year or two to this code, I 
			# wouldn't have a clue what was going on.  By 
			# putting them in variables (less efficient), I 
			# make my life easier in the future.
			rpower = float(rxList[1])
			CurrentPower = rpower
			DayMaxPower = max(DayMaxPower,CurrentPower)
			DayMinPower = min(DayMinPower,CurrentPower)
			apower = float(rxList[2])
			pfactor = float(rxList[3])
			voltage = float(rxList[4])
			current = float(rxList[5])
			frequency = float(rxList[6].rstrip())
			#print ('rpower %s, apower %s, pfactor %s, voltage %s, current %s, frequency %s' 
			#	%(rpower, apower, pfactor, voltage, current, frequency))
			try:
				dbconn = sqlite3.connect(DATABASE)
				c = dbconn.cursor()
				c.execute("update power set rpower = ?, "
					"apower = ?,"
					"pfactor = ?,"
					"voltage = ?,"
					"current = ?,"
					"frequency = ?,"
					"utime = ?;",
					(rpower, apower, pfactor, voltage, current, 
					frequency, time.strftime("%A, %B, %d at %H:%M:%S")))
				dbconn.commit()
			except:
				print "Error: Database error"
			dbconn.close()
		elif rxList[0] == 'Septic':
			#print("Got Septic Packet")
			#print(rxList)
			dbconn = sqlite3.connect(DATABASE)
			c = dbconn.cursor()
			c.execute("update septic set level = ?, utime = ?;",
				(rxList[1].rstrip(), time.strftime("%A, %B, %d at %H:%M:%S")))
			dbconn.commit()
			dbconn.close()
		elif rxList[0] == 'Freezer':
			lprint ("Got a Freezer Packet", rxList)
			
		else:
			print ("Error: can\'t handle " + rxList[0] + ' yet')
			for item in rxList:
				print item,
			print
			pass
	elif data['id'] == 'rx_io_data_long_addr':
		#print ('Got Outside Thermometer Packet')
		tmp = data['samples'][0]['adc-1']
		# Don't even ask about the calculation below
		# it was a real pain in the butt to figure out
		otemp = (((tmp * 1200.0) / 1024.0) / 10.0) * 2.0
		CurrentOutTemp = otemp
		DayOutMaxTemp = max(DayOutMaxTemp, CurrentOutTemp)	
		DayOutMinTemp = min(DayOutMinTemp, CurrentOutTemp)
		dbconn = sqlite3.connect(DATABASE)
		c = dbconn.cursor()
		c.execute("update xbeetemp set 'currenttemp' = ?, "
			"utime = ?;",
			(int(otemp),
			time.strftime("%A, %B, %d at %H:%M:%S")))
		dbconn.commit()
		dbconn.close()
	else:
		print ('Error: Unimplemented XBee frame type ' + data['id'])

#-------------------------------------------------

# This little status routine gets run by scheduler
# periodically seconds
def printHouseData():
	lprint('Power Data: Current %s, Min %s, Max %s'
		%(int(float(CurrentPower)), int(float(DayMinPower)), int(float(DayMaxPower))))
	lprint('Outside Temp: Current %s, Min %s, Max %s'
		%(int(float(CurrentOutTemp)), int(float(DayOutMinTemp)), int(float(DayOutMaxTemp))))
	print

def handleCommand(command):
	# the command comes in from php as something like
	# ('s:17:"AcidPump, pumpOff";', 2)
	# so command[0] is 's:17:"AcidPump, pumpOff'
	# then split it at the "  and take the second item
	# inter language stuff is a real pain sometimes
	#print command
	try:
		c = str(command[0].split('\"')[1]).split(',')
	except IndexError:
		c = str(command[0]).split(' ')	  #this is for something I sent from another process
	#print c
	device = c[0]
	todo = c[1].strip(' ')
	# now I have a list like ['device', 'command']
	if device == 'AcidPump':
		lprint ("AcidPump command", todo)
		if (todo == "pumpOn"):
			lprint ("pump on")
			sendPacket(BROADCAST, "AcidOn\r")
		elif (todo == "pumpOff"):
			lprint ("pump off")
			sendPacket(BROADCAST, "AcidOff\r")
		elif (todo == "AcidStatus"):
			lprint ("pump status")
			sendPacket(BROADCAST, "AcidStatus\r")
		else:
			lprint ("can't do this yet")
	elif device == 'Pool':
		lprint ("Pool command: ", todo)
		if (todo == "lighton"):
			lprint ("lighton")
			sendPacket(BROADCAST, "pool,L\r")
		elif (todo == "lightoff"):
			lprint ("lightoff")
			sendPacket(BROADCAST, "pool,l\r")
		elif (todo == "waterfallon"):
			lprint ("waterfall on")
			sendPacket(BROADCAST, "pool,W\r")
		elif (todo == "waterfalloff"):
			lprint ("waterfall off")
			sendPacket(BROADCAST, "pool,w\r")
		elif (todo == "fountainon"):
			lprint ("fountain on")
			sendPacket(BROADCAST, "pool,F\r")
		elif (todo == "fountainoff"):
			lprint ("fountain off")
			sendPacket(BROADCAST, "pool,f\r")
		elif (todo == "pumpoff"):
			lprint ("pump off")
			sendPacket(BROADCAST, "pool,o\r")
		elif (todo == "pumphigh"):
			lprint ("pump high")
			sendPacket(BROADCAST, "pool,S\r")
		elif (todo == "pumplow"):
			lprint ("pump low")
			sendPacket(BROADCAST, "pool,s\r")
		elif (todo == "controlreset"):
			lprint ("control reset")
			sendPacket(BROADCAST, "pool,b\r")
		else:
			lprint ("haven't done this yet", device, todo)
	elif device == 'Garage':
		lprint ("Garage command", todo)
		if (todo == 'waterhon'):
			sendPacket(BROADCAST, "Garage,waterheateron\r")
		elif (todo == 'waterhoff'):
			sendPacket(BROADCAST, "Garage,waterheateroff\r")
		elif (todo == 'door1open'):
			sendPacket(BROADCAST, "Garage,door1\r")
		elif (todo == 'door1close'):
			sendPacket(BROADCAST, "Garage,door1\r")
		elif (todo == 'door2open'):
			sendPacket(BROADCAST, "Garage,door2\r")
		elif (todo == 'door2close'):
			sendPacket(BROADCAST, "Garage,door2\r")
		else:
			lprint ("haven't done this yet")
	elif device == "preset":
		if (todo == "test"): # This is only to test the interaction
			lprint ("got a preset test command")
		elif (todo =='acoff'):
			controlThermo("North", "off")
			controlThermo("South", "off")
			controlThermo("North", "fan=auto")
			controlThermo("South", "fan=auto")
		elif (todo == 'recirc'):
			controlThermo("North", "fan=recirc")
			controlThermo("South", "fan=recirc")
		elif (todo == 'auto'):
			controlThermo("North", "fan=auto")
			controlThermo("South", "fan=auto")
		elif (todo == 'temp98'):
			controlThermo("North", "temp=98")
			controlThermo("South", "temp=98")
			controlThermo("North", "fan=auto")
			controlThermo("South", "fan=auto")
		elif (todo == 'summernight'):
			controlThermo("North", "temp=78")
			controlThermo("South", "temp=79")
			controlThermo("North", "fan=recirc")
			controlThermo("South", "fan=recirc")
			controlThermo("North", "cool")
			controlThermo("South", "cool")
		elif (todo == 'winternight'):
			controlThermo("North", "temp=73")
			controlThermo("South", "temp=72")
			controlThermo("North", "fan=recirc")
			controlThermo("South", "fan=recirc")
			controlThermo("North", "heat")
			controlThermo("South", "heat")
		elif (todo == 'peakno'):
			controlThermo("North", "peakoff")
			controlThermo("South", "peakoff")
		elif (todo == 'peakyes'):
			controlThermo("North", "peakon")
			controlThermo("South", "peakon")
		else:
			lprint ("haven't done this yet")
	else:
		lprint ("command not implemented: ", str(c))
	
#-----------------------------------------------------------------
# get the stuff from the houserc file
hv = getHouseValues()
#------------ XBee Stuff -------------------------
XBEEPORT = hv["xbeeport"]
packets = Queue.Queue() # When I get a packet, I put it on here
# Open serial port for use by the XBee
XBEEBAUD_RATE = 9600
ser = serial.Serial(XBEEPORT, XBEEBAUD_RATE)

# the database where I'm storing stuff
DATABASE = hv["database"]



# The XBee addresses I'm dealing with
BROADCAST = '\x00\x00\x00\x00\x00\x00\xff\xff'
UNKNOWN = '\xff\xfe' # This is the 'I don't know' 16 bit address

#-------------------------------------------------
logging.basicConfig()

# Create XBee library API object, which spawns a new thread
zb = ZigBee(ser, callback=message_received)

#This is the main thread.  Since most of the real work is done by 
# scheduled tasks, this code checks to see if packets have been 
# captured and calls the packet decoder

# This process also handles commands sent over the XBee network 
# to the various devices.  I want to keep the information on the
# exact commands behind the fire wall, so they'll come in as 
# things like 'AcidPump, on', 'Garage, dooropen'
# since this is a multiprocess environment, I'm going to use 
# system v message queues to pass the commands to this process

# Create the message queue where commands can be read
# I just chose an identifier of 12.	 It's my machine and I'm
# the only one using it so all that crap about unique ids is
# totally useless.	12 is the number of eggs in a normal carton.
Cqueue = sysv_ipc.MessageQueue(12, sysv_ipc.IPC_CREAT,mode=0666)

# a priming read for the thermostats
ThermostatStatus()
#------------------Stuff I schedule to happen -----
scheditem = BackgroundScheduler()

# every 30 seconds print the most current power info
# This only goes into the job log so I can see that
# the device is alive and well.
scheditem.add_job(printHouseData, 'interval', seconds=30)
# schedule reading the thermostats for every thirty seconds
scheditem.add_job(ThermostatStatus, 'interval', seconds=10)
scheditem.start()

firstTime = True;
lprint ("Started")

while True:

	try:
		time.sleep(0.1)
		sys.stdout.flush() # if you're running non interactive, do this
		if packets.qsize() > 0:
			# got a packet from recv thread
			# See, the receive thread gets them
			# puts them on a queue and here is
			# where I pick them off to use
			newPacket = packets.get_nowait()
			# now go dismantle the packet
			# and use it.
			handlePacket(newPacket)
		try:
			if (firstTime):
				while(True):
					try:
						# commands could have piled up while this was 
						# not running.	Clear them out.
						junk = Cqueue.receive(block=False, type=0)
						lprint ("purging leftover commands", str(junk)) 
					except sysv_ipc.BusyError:
						break
				firstTime=False
			newCommand = Cqueue.receive(block=False, type=0)
			# type=0 above means suck every message off the
			# queue.  If I used a number above that, I'd
			# have to worry about the type in other ways.
			# note, I'm reserving type 1 messages for 
			# test messages I may send from time to 
			# time.	 Type 2 are messages that are
			# sent by the php code in the web interface.
			# Type 3 are from the event handler.
			# I haven't decided on any others yet.
			handleCommand(newCommand)
		except sysv_ipc.BusyError:
			pass # Only means there wasn't anything there

	except KeyboardInterrupt:
			break

# halt() must be called before closing the serial
# port in order to ensure proper thread shutdown
zb.halt()
ser.close()

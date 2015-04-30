#! /usr/bin/python
from apscheduler.schedulers.background import BackgroundScheduler
import sys
import datetime
import logging
import time
import sqlite3
import httplib, urllib
from houseutils import getHouseValues, lprint, dbTime

# this is for putting things in the log file
def lprint(text):
	print dbTime(),text
	sys.stdout.flush()

# This is where the update to ThingSpeak happens
def updateThingSpeak():
	lprint ("Updating ThingSpeak ")
	# open the database
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	# Getting it out of the database a field at a time
	# is probably less efficient than getting the whole record,
	# but it works.  
	#
	# On ThingSpeak I only update real power, power factor, voltage,
	# frequency, outside temperature and inside temperature
	# so I'm simply going to put the values in variables instead of
	# some complex (and probably faster) compound statement.
	outsideTemp = c.execute(
		"select temperature from Barometer").fetchone()[0]
	# This a really cool thing about some languages
	# the variable types are dynamic, so I can just change it
	# from a string to a int on the fly.
	outsideTemp = int(float(outsideTemp) +.5)
	power = c.execute(
		"select rpower from power").fetchone()[0]
	power = int(float(power)+.5)
	voltage = c.execute(
		"select voltage from power").fetchone()[0]
	voltage = int(float(voltage)+.5)
	apparentPower = c.execute(
		"select apower from power").fetchone()[0]
	apparentPower = float(apparentPower)
	current = c.execute(
		"select current from power").fetchone()[0]
	current = int(float(current)+.5)
	frequency = c.execute(
		"select frequency from power").fetchone()[0]
	frequency = float(frequency)
	powerFactor = c.execute(
		"select pfactor from power").fetchone()[0]
	powerFactor = float(powerFactor)
	insideTemp = c.execute(
		"select avg(\"temp-reading\") from thermostats").fetchone()[0]
	insideTemp = int(float(insideTemp)+.5)
	# OK, got all the stuff I want to update
	dbconn.close() # close the data base in case the HTTP update fails
	#
	# This is a debug statement that I put in to show
	# not only what the values were, but also how they
	# can be formatted.
	# print ("Power = %d \nVoltage = %d \nApparent Power = %d "
			# "\nCurrent = %d \nFrequency %.2f \nPower Factor = %.2f "
			# "\nOutside Temp = %d \nInside Temp = %d" %
			# (power, voltage, apparentPower, current,
			# frequency, powerFactor, outsideTemp, insideTemp))
			
	# OK, now I've got all the data I want to record on ThingSpeak
	# So, I have to get involved with that thing called a REST interface
	# It's actually not too bad, it's just the way people pass 
	# data to a web page, you see it all the time if you watch
	# how the URL on your browser changes.
	#
	# urlencode takes a python tuple as input, but I just create it
	# as a parameter so you can see what it really is.
	params = urllib.urlencode({'field1': power, 'field2':powerFactor,
				'field3':voltage, 'field4':frequency, 
				'field5':insideTemp, 'field6':outsideTemp,
				'key':thingSpeakKey})
	# if you want to see the result of the url encode, just uncomment
	# the line below.  This stuff gets confusing, so give it a try
	#print params
	#
	# Now, just send it off as a POST to ThingSpeak
	headers = {"Content-type": "application/x-www-form-urlencoded","Accept": "text/plain"}
	try:
		# there are times that the internet times out on this kind of thing
		# this will just skip the update and show a message in the log
		conn = httplib.HTTPConnection("api.thingspeak.com:80", timeout=30)
		conn.request("POST", "/update", params, headers)
	except:
		lprint ("error: " + str(sys.exc_info()[0]))
		return
	response = conn.getresponse()
	#print "Thingspeak Response:", response.status, response.reason
	# I only check for the 'OK' in the reason field.  That's 
	# so I can print a failure to any log file I happen to set 
	# up.  I don't want to print a lot of stuff that I have to
	# manage somehow.
	if (response.reason != 'OK'):
		lprint ("Error, " + str(response.status) + " " + str(response.reason))
		return # without updating the database
	conn.close
	# Now that everything worked, update the time in the database
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	c.execute("update thingspeak set utime=?;",(dbTime(),))
	dbconn.commit()
	dbconn.close() # close the data base

	
# This is where the main code begins.  Notice how basically nothing
# happens here?  I simply show a sign on message, set up logging, and
# start a scheduled task to actually do the work.
lprint ("started")
logging.basicConfig()

hv = getHouseValues()
thingSpeakKey = hv["thingspeak"]["key"]
# the database where I'm storing stuff
DATABASE= hv["database"]

#------------------Stuff I schedule to happen -----
scheditem = BackgroundScheduler()
scheditem.start()
# every minute update the data store on ThingSpeak
scheditem.add_job(updateThingSpeak, 'interval', seconds=60)

updateThingSpeak() # do it now so I don't have to wait when debugging
while True:
	time.sleep(20) #This doesn't matter much since it is schedule driven

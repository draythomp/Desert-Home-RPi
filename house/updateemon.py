#! /usr/bin/python
from apscheduler.schedulers.background import BackgroundScheduler
import sys
import datetime
import logging
import time
import sqlite3
import httplib, urllib
from houseutils import getHouseValues, lprint

# This is where the update to ThingSpeak happens
def updateEmonCms():
	lprint ("Updating emoncms ")
	sys.stdout.flush()
	# open the database
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	# Getting it out of the database a field at a time
	# is probably less efficient than getting the whole record,
	# but it works.  
	#
	# On emoncms I update real power, power factor, voltage,
	# frequency, outside temperature and inside temperature
	# so I'm simply going to put the values in variables instead of
	# some complex (and probably faster) compound statement.
	outsideTemp = c.execute(
		"select currenttemp from xbeetemp").fetchone()[0]
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
	dbconn.close() # close the data base in case the HTTP handoff fails
	#
	# This is a debug statement that I put in to show
	# not only what the values were, but also how they
	# can be formatted.
	# print ("Power = %d \nVoltage = %d \nApparent Power = %d "
			# "\nCurrent = %d \nFrequency %.2f \nPower Factor = %.2f "
			# "\nOutside Temp = %d \nInside Temp = %d" %
			# (power, voltage, apparentPower, current,
			# frequency, powerFactor, outsideTemp, insideTemp))
			
	# OK, now I've got all the data I want to record on emoncms
	# so I have to put it in json form.  json isn't that hard if you 
	# don't have multiple levels, so I'll just do it with a string
	# format.  It's just a set of ordered pairs for this.
	params = ("RealPower:%d,PowerFactor:%.2f,"
				"PowerVoltage:%d,PowerFrequency:%.2f,"
				"InsideTemp:%d,OutsideTemp:%d" %
				(power,powerFactor,voltage,frequency,insideTemp,
				outsideTemp))
	# if you want to see the result of the formatting, just uncomment
	# the line below.  This stuff gets confusing, so give it a try
	#print params
	#
	# Now, just send it off to emoncms
	try:
		# I had to add the timeout parameter to allow for internet problems.
		conn = httplib.HTTPConnection("emoncms.org:80", timeout=45)
		request = "/input/post?apikey=" + EMONKEY + "&" + "json=" + params
		#print request
		# emoncms uses a GET not a POST
		conn.request("GET", request)
	except:
		lprint ("error: " + str(sys.exc_info()[0]))
		return
	response = conn.getresponse()

	#print "emoncms Response:", response.status, response.reason
	# I only check for the 'OK' in the reason field.  That's 
	# so I can print a failure to any log file I happen to set 
	# up.  I don't want to print a lot of stuff that I have to
	# manage somehow.  However, emoncms seldom returns an error,
	# I messed this interaction up a number of times and never got
	# an error.  
	if (response.reason != 'OK'):
		lprint ("error, " + str(response.status) + " " + str(response.reason))
		return # without update to the database
	conn.close
	# Now that everything worked, update the time in the database
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	c.execute("update emoncms set utime=?;",(time.strftime("%A, %B, %d at %H:%M:%S"),))
	dbconn.commit()
	dbconn.close() # close the data base

	
# This is where the main code begins.  Notice how basically nothing
# happens here?  I simply show a sign on message, set up logging, and
# start a scheduled task to actually do the work.
lprint ("started")
logging.basicConfig()
# get the values I need from the rc file
# The Xively feed id and API key that is needed
hv = getHouseValues()
EMONKEY = hv["emoncms"]["key"]
# the database where I'm storing stuff
DATABASE= hv["database"]

#------------------Stuff I schedule to happen -----
scheditem = BackgroundScheduler()
scheditem.start()
# every minute update the data store on ThingSpeak
scheditem.add_job(updateEmonCms, 'interval', seconds=60)
#do it now so we don't have to wait when debugging
updateEmonCms() 
while True:
	time.sleep(20) #This doesn't matter much since it is schedule driven

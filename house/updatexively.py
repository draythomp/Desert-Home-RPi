#!/usr/bin/python
import xively
import sys
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import logging
import time
import sqlite3
from houseutils import getHouseValues, lprint

# This is where the update to Xively happens
def updateXively():
	lprint ("Updating Xively ")
	sys.stdout.flush()

	# Currently I have to use UTC for the time,
	# there's a bug somewhere in the library or 
	# Xively.  It doesn't matter though because
	# it's easy to convert
	now = datetime.datetime.utcnow()
	# open the database
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	# Yes, there are better ways to do the stuff below,
	# but I wanted to use a single statement to get it 
	# from the data base an update the field going to 
	# Xively.  It turns out that is is a rather odd
	# looking statement, but it works.
	# However, I noticed that fetchone() returns a tuple
	# with only one value in it (value,) which means
	# I have to get at it with a [0].  
	tmp = c.execute("select motor from pool").fetchone()[0];
	if (tmp == 'High'): # a little special handling for the pool motor
		motor = 2
	elif (tmp == 'Low'):
		motor = 1
	else:
		motor = 0
	feed.datastreams = [
        xively.Datastream(id='outside_temp', 
			current_value = c.execute(
				"select currenttemp from xbeetemp")
				.fetchone()[0], 
			at=now),
		xively.Datastream(id='power_usage', 
			current_value = c.execute(
				"select rpower from power")
				.fetchone()[0],  
			at=now),
		xively.Datastream(id='voltage', 
			current_value = c.execute(
				"select voltage from power")
				.fetchone()[0],  
			at=now),
		xively.Datastream(id='apparent_power', 
			current_value = c.execute(
				"select apower from power")
				.fetchone()[0],  
			at=now),
		xively.Datastream(id='current', 
			current_value = c.execute(
				"select current from power")
				.fetchone()[0],  
			at=now),
		xively.Datastream(id='frequency', 
			current_value = c.execute(
				"select frequency from power")
				.fetchone()[0],  
			at=now),
		xively.Datastream(id='power_factor', 
			current_value = c.execute(
				"select pfactor from power")
				.fetchone()[0],  
			at=now),
		xively.Datastream(id='inside_temp',
			current_value = c.execute(
				"select avg(\"temp-reading\") from thermostats")
			.fetchone()[0],
			at=now),
		xively.Datastream(id='pool_motor',
			current_value = motor,
			at=now),
		xively.Datastream(id='pool_temp',
			current_value = c.execute(
				"select ptemp from pool")
			.fetchone()[0],
			at=now)
		]
	try:
		feed.update()  # and update Xively with the latest
		# update the time in the database
		c.execute("update xively set utime=?;",(time.strftime("%A, %B, %d at %H:%M:%S"),))
		dbconn.commit()
		dbconn.close() # close the data base
	except:
		lprint ("error: " + str(sys.exc_info()[0]))

lprint ("started")
# get the values I need from the rc file
# The Xively feed id and API key that is needed
hv = getHouseValues()
FEED_ID = hv["xively"]["feed"]
API_KEY = hv["xively"]["key"]
# the database where I'm storing stuff
DATABASE= hv["database"]

logging.basicConfig()

#------------------Stuff I schedule to happen -----
scheditem = BackgroundScheduler()
scheditem.start()
# every minute update the data store on Xively
# may have to use max_instances to allow for web problems
scheditem.add_job(updateXively, 'interval', seconds=60, max_instances=2)
#--------------------Xively interface----------------
# Initialize Xively api client
api = xively.XivelyAPIClient(API_KEY)
# and get my Xively feed
feed = api.feeds.get(FEED_ID)
# I do this at the beginning because, when debugging, I don't want to wait
updateXively()
while True:
	time.sleep(20) #This doesn't matter much since it is schedule driven

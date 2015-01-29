#!/usr/bin/python
import time
from time import sleep
from datetime import datetime
import sys
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from simplejson import encoder as jsonEncoder
import httplib
import StringIO
import gzip
import sqlite3
import pprint
from houseutils import getHouseValues, lprint

#If you want lots of messages and debug information
# set this to true
DEBUG = False

# the site accepts compression, might as well use it
def compressBuf(buf):
	zbuf = StringIO.StringIO()
	zfile = gzip.GzipFile(mode = 'wb',	fileobj = zbuf, compresslevel = 9)
	zfile.write(buf)
	zfile.close()
	return zbuf.getvalue()

def updateGrovestreams():
	# This is VERY different from their examples.  I named
	# my streams with something I could understand and read
	# Probably not the best way to do it, but it works really
	# well for me.
	component_id = "desert-home-id"
	rpowerStream_id = "power_usage"
	otempStream_id = "outside_temp"
	apowerStream_id = "apparent_power"
	voltageStream_id = "voltage"
	currentStream_id = "current"
	pfactorStream_id = "power_factor"
	itempStream_id = "inside_temp"
	ptempStream_id = "pool_temp"
	pmotorStream_id = "pool_motor"
	frequencyStream_id = "frequency"
	
	# This object really helps when displaying
	# the rather complex data below
	pp = pprint.PrettyPrinter(depth=10)
	
	#get the millis since epoch
	# in unix the epoch began back in 1970, look it up
	now = datetime.now()
	nowEpoch = int(time.mktime(now.timetuple())) * 1000
	
	#assemble feed and convert it to a JSON string
	feed = {};
	feed['feed'] = {}
	feed['feed']['component'] = []
	if DEBUG:
		pp.pprint(feed)
		print
		sys.stdout.flush()
	
	comp = {}
	comp['stream'] = []
	comp['componentId'] = component_id
	feed['feed']['component'].append(comp)
	if DEBUG:
		pp.pprint(feed)
		print
		sys.stdout.flush()
	
	# Now I'm going to fill in the stream values, open database
	# I took a brute force approach to building the dictionary that
	# is converted into JSON.  I could have been much more elegant
	# in building it, but the folks just starting out would have
	# had a tough time understanding it
	dbconn = sqlite3.connect(DATABASE)
	c = dbconn.cursor()
	# So, you make a stream to stuff things into.  It's actually
	# a python dictionary that we'll pass to a JSON encoder a ways
	# down into the code.  I'll be adding entries to this as I pull
	# items out of the database
	stream1 = {}  
	stream1['streamId'] = rpowerStream_id
	stream1['time'] = [] 
	stream1['data'] = []
	comp['stream'].append(stream1)
	
	current_value = c.execute("select rpower from power").fetchone()[0]	 
	stream1['time'].append(nowEpoch)
	stream1['data'].append(float(current_value))
	# this is a cool way to debug this kind of thing.
	if DEBUG:
		pp.pprint(feed)
		print
		sys.stdout.flush()
	# notice how I get an item out of the database
	# and add it to the dictionary.  I'll do this
	# several times
	stream2 = {}
	stream2['streamId'] = otempStream_id
	stream2['time'] = []
	stream2['data'] = []
	comp['stream'].append(stream2)
	current_value = c.execute(
		"select temperature from Barometer").fetchone()[0]
	stream2['time'].append(nowEpoch)
	stream2['data'].append(float(current_value))

	stream3 = {}
	stream3['streamId'] = apowerStream_id
	stream3['time'] = []
	stream3['data'] = []
	comp['stream'].append(stream3)
	current_value = c.execute(
			"select apower from power").fetchone()[0]
	stream3['time'].append(nowEpoch)
	stream3['data'].append(float(current_value))

	stream4 = {}
	stream4['streamId'] = voltageStream_id
	stream4['time'] = []
	stream4['data'] = []
	comp['stream'].append(stream4)
	current_value = c.execute(
			"select voltage from power").fetchone()[0]
	stream4['time'].append(nowEpoch)
	stream4['data'].append(float(current_value))

	stream5 = {}
	stream5['streamId'] = currentStream_id
	stream5['time'] = []
	stream5['data'] = []
	comp['stream'].append(stream5)
	current_value = c.execute(
			"select current from power").fetchone()[0]
	stream5['time'].append(nowEpoch)
	stream5['data'].append(float(current_value))

	stream6 = {}
	stream6['streamId'] = pfactorStream_id
	stream6['time'] = []
	stream6['data'] = []
	comp['stream'].append(stream6)
	current_value = c.execute(
			"select pfactor from power").fetchone()[0]
	stream6['time'].append(nowEpoch)
	stream6['data'].append(float(current_value))

	stream7 = {}
	stream7['streamId'] = itempStream_id
	stream7['time'] = []
	stream7['data'] = []
	comp['stream'].append(stream7)
	current_value = c.execute(
			"select avg(\"temp-reading\") from thermostats").fetchone()[0]
	stream7['time'].append(nowEpoch)
	stream7['data'].append(float(current_value))

	stream8 = {}
	stream8['streamId'] = ptempStream_id
	stream8['time'] = []
	stream8['data'] = []
	comp['stream'].append(stream8)
	current_value = c.execute(
			"select ptemp from pool").fetchone()[0]
	stream8['time'].append(nowEpoch)
	stream8['data'].append(float(current_value))

	stream9 = {}
	stream9['streamId'] = pmotorStream_id
	stream9['time'] = []
	stream9['data'] = []
	comp['stream'].append(stream9)
	tmp = c.execute("select motor from pool").fetchone()[0];
	if (tmp == 'High'): # a little special handling for the pool motor
		motor = 2
	elif (tmp == 'Low'):
		motor = 1
	else:
		motor = 0
	stream9['time'].append(nowEpoch)
	stream9['data'].append(int(motor))

	stream10 = {}
	stream10['streamId'] = frequencyStream_id
	stream10['time'] = []
	stream10['data'] = []
	comp['stream'].append(stream10)
	current_value = c.execute(
			"select frequency from power").fetchone()[0]
	stream10['time'].append(nowEpoch)
	stream10['data'].append(float(current_value))

	# all the values are filled in, close the database
	# update the time in the database
	c.execute("update grovestream set utime=?;",(time.strftime("%A, %B, %d at %H:%M:%S"),))
	dbconn.commit()
	dbconn.close() # close the data base
	# This will print the entire dictionary I just constructed
	# so you can see what is going on
	if DEBUG:
		pp.pprint(feed)
		print
		sys.stdout.flush()
	# exit() # I put this in for debugging.  It exits before
	# the JSON string is constructed and sent off to grovestreams
	# Of course you want to keep it commented until needed
	#
	# And this is where the JSON string is built
	encoder = jsonEncoder.JSONEncoder()
	json = encoder.encode(feed);
	# and this will print it so you can see what is happening
	if DEBUG:
		print json # for debugging
		print
		sys.stdout.flush()

	#Upload the feed
	try:
		lprint ("Updating GroveStream")
		conn = httplib.HTTPConnection('www.grovestreams.com', timeout=10)

		url = '/api/feed?&org=%s&api_key=%s' % (org, api_key)

		compress = True
		if compress:
			body = compressBuf(json)
			headers = {"Content-type": "application/json", "Content-Encoding" : "gzip"}
		else:
			body = json
			headers = {"Content-type": "application/json", "charset":"UTF-8"}

		conn.request("PUT", url, body, headers)
				
		response = conn.getresponse()
		status = response.status
				
		if status != 200 and status != 201:
			try:
				if (response.reason != None):
					lprint('reason: ' + response.reason + ' body: ' + response.read())
				else:
					lprint('body: ' + response.read())
			except Exception:
				lprint('HTTP Fail Status: %d' % (status) )
				return
			
	except Exception as e:
		lprint('HTTP Send Error: ' + str(e))
		return
   
	finally:
		if conn != None:
			conn.close()
				
# I just discovered the statement below.
# someday I'll have go figure out what it really does.				
if __name__ == '__main__':
	lprint ("started")
	logging.basicConfig()
	# get the values I need from the rc file
	# The grovestreams organization and api key are needed
	# but the darn things wind up being unicode.  I didn't want
	# to get into a long discussion of what character set to use, 
	# etc. or worry about what decoder to use in the json load.
	# The explanations go on forever and ever.
	# So, I just convert them into strings and go on from there
	hv = getHouseValues()
	org = str(hv["grovestreams"]["org"])
	api_key = str(hv["grovestreams"]["apiKey"])
	# the database where I'm storing stuff
	DATABASE= hv["database"]


	#------------------Stuff I schedule to happen -----
	scheditem = BackgroundScheduler()
	scheditem.start()
	# every minute update the data store on Xively
	scheditem.add_job(updateGrovestreams, 'interval', seconds=60, max_instances=1)
	#
	# A couple of people asked me why I put this statement in
	# since I have it scheduled to happen every 60 seconds already
	# Well, when you're debugging something it sucks to have to
	# wait 60 seconds to see if you fixed it, so I do it 
	# first, then let the scheduler take care of the rest.
	#
	updateGrovestreams()
	while True:
		time.sleep(20) #This doesn't matter much since it is schedule driven
	 

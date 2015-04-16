import json
import time
import sys

# I send the local time in seconds since the linux epoch
# around the house to keep things in sync and control various
# default timers on the devices.  This turns out to be a problem 
# since linux expects time to be in UTC.  So, this routine returns
# a formatted string to use when I update the database with a
# time taken from one of the devices.
#
# The idea is that I want to be able to read various items without
# spending time converting time zones or seconds from 1970.  It
# helps a lot when trying to chase down a bug.  If seconds is not
# specified, it will return the current time formated for the 
# database.  Also, I got tired of keeping track of the time format.
def dbTime(seconds=None):
    if seconds is not None:
        t = time.localtime(float(seconds) + time.timezone)
    else:
        t = time.localtime()
    return time.strftime("%A, %B, %d, at %H:%M:%S",t)

# returns an ascii string representing the unix ipoch time. I use
# it to key records on the database based on the time it happens.
def dbTimeStamp(seconds=None):
    if seconds is not None:
        t = int(seconds)
    else:
        t = int(time.time())
    return str(t)
    
# This will return the unix epoch time for midnight of the day asked for
# relative to today. Send a 1 when you want yesterday, a null for today, 
# a 7 for a week ago, etc. I use it for weather readings over time.
def midnight(when=None):
    if (when==None):
        t = datetime.now()
    else:
        t = datetime.now() - timedelta(days=when)
    # set the hours, mins, sec etc. to zero to represent midnight
    midnight = t.now().replace \
        (hour=0, minute=0, second=0, microsecond=0)
    # now convert that to unix epoch time
    # and return a string to use
    return str(int(time.mktime(midnight.timetuple())))
    
# See http://www.desert-home.com/2014/10/using-rc-file-in-my-system.html
# for a description of the .houserc file I use.
def getHouseValues():
	json_data=open("/home/pi/.houserc").read()
	return json.loads(json_data)

# I use this print routine to log the date and time for things that happen
# When software runs for several days without attention, the date and time 
# something happened becomes important.
def lprint(farg, *argv):
	print time.strftime("%A, %B, %d at %H:%M:%S"),
	print farg,
	for arg in argv:
		print arg,
	print
	sys.stdout.flush()
    
# See http://www.desert-home.com/2014/10/my-tiny-timer-class.html
# for a description of how to use this timer.
class timer:
	_things = []
	
	def __init__(self, callback, seconds=1, minutes=0, hours=0):
		interval = (hours*60*60) + (minutes*60) + seconds
		actionTime = time.time() + interval
		self._things.append({"callback":callback,"interval":interval,"actionTime":actionTime})

	def tick(self):
		now = time.time()
		for i in self._things:
			if i["callback"] == None:
				continue
			if now >= i["actionTime"]:
				i["callback"]()
				i["actionTime"] += i["interval"]

checkTimer = timer(None)

''' This is code to test and illustrate the timer '''
def printSecond():
	print "second"
	
def printTwoSeconds():
	print "twoseconds"

def printMinute():
	print "minute"

if __name__ == "__main__":
	import pprint
	pprint.pprint(getHouseValues())
	lprint ("hello", "there", "you all", 1,2, 1.2)
	lprint ("Odd Error: %s" % 123)
	lprint("Error: cannot retrieve URL: " + str(7) + ": " + "something")
	
	# First create any timers you need
	oneSecond = timer(printSecond, seconds=1)
	twoSeconds = timer(printTwoSeconds, seconds=2)
	minute = timer(printMinute, minutes=1)
	
	# now once in a while call tick to let them happen
	while True:
		checkTimer.tick()
		# a sleep lets the cpu have a rest to do other things.
		time.sleep(0.5)

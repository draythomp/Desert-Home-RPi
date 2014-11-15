#! /usr/bin/python
'''
This is an experiment using cherrypy.  It's a minimal web server to 
make web services easier to implement.  My use of it is to allow interprocess 
comm easier to implement.  Additionally, you can interface with it directly 
using a browser.  That should help in debugging various items when they act
up around the house.

It should also allow the various processes to be split between machines.
One machine could handle the lights, another the appliances, etc.  You should
be able to expand a home control network forever.

This will bring up a web server on the address and port number specified in 
the .houserc file like this:

"wemo":{
"ipAddress":"192.168.0.205",
"port": 51001},

So 'http"//192.168.0.205:5101' will get a 'hello world' response while the 
terminal that started it will get a series of 'tick.'  This illustrates that it
can respond to http and do something else at the same time.

This is only an experiment before combining the code into my home.  It's going 
to control the wemo light switches first, and then based on that, expand to
the other devices around the house.  That's why the wemo references in the
file.

'''
import cherrypy
# I use my house utilities in the test (houseutils.py), so I have to mess
# around a bit to get the file imported.
import os, sys
lib_path = os.path.abspath('../house')
sys.path.append(lib_path)
from houseutils import lprint, getHouseValues, timer, checkTimer

# This is where the actual 'Hello World' goes out to the browser
class WemoSC(object):
    @cherrypy.expose
    def index(self):
        return "Hello world!"
    
# This is the callback for my simple timer class
def ticker():
    lprint ("tick")
    
if __name__ == '__main__':
    # This timer will handle something on a periodic basis
    # Things like polling lights to see what they're doing right now
    jobTimer = timer(ticker, seconds=2)

    # Get the ip address and port number you want to use
    # from the houserc file
    ipAddress=getHouseValues()["wemo"]["ipAddress"]
    port = getHouseValues()["wemo"]["port"]
    # Now configure the cherrypy server using the values
    cherrypy.config.update({'server.socket_host' : ipAddress,
                            'server.socket_port': port,
                            'engine.autoreload_on': False,
                            })
    # Subscribe to the 'main' channel in cherrypy with my timer
    # tuck so the timers I use get updated
    cherrypy.engine.subscribe("main", checkTimer.tick)
    # Now just hang on the HTTP server looking for something to 
    # come in.  The cherrypy dispatcher will update the things that
    # are subscribed which will update the timers so the light
    # status gets recorded.
    cherrypy.quickstart(WemoSC())

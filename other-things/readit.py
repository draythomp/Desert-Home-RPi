#!/usr/bin/python
import sys
import json
import time

buff = ''
while True:
    try:
        buff += sys.stdin.read(1)
        if buff.endswith('\n'):
            data = json.loads(buff[:-1])
            print "On", time.strftime("%A, %B, %d at %H:%M:%S",time.localtime(float(data["windSpeed"]["t"]))),
            print "the wind was blowing from the", data["windDirection"]["WD"],
            print "at\n", data["windSpeed"]["WS"], "mph,",
            print "and it is", data["temperature"]["T"], "degrees F Outside.",
            print "The humidity is", data["humidity"]["H"], "percent",
            print "and \nthe rain counter is", data["rainCounter"]["RC"],
            print
            sys.stdout.flush()
            buff = ''
    except KeyboardInterrupt:
        sys.stdout.flush()
        sys.exit()
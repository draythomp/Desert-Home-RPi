#!/usr/bin/python
import sys, os
from datetime import datetime, timedelta
from houseutils import getHouseValues, lprint, dbTime
from time import localtime, strftime
import paho.mqtt.client as mqtt

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, rc):
    print("Connected to mqtt broker with result code "+str(rc))
    sys.stdout.flush()
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe([("Desert-Home/Log",0),("Desert-Home/Attention",0)])

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    print(dbTime()+' '+str(msg.payload))
    sys.stdout.flush()

#-------------------------------------------------  
processName = os.path.basename(sys.argv[0])
print processName + " Starting"
# get the values out of the houserc file
hv = getHouseValues()
mqttServer = hv["mqttserver"]
mqttc = mqtt.Client(client_id=processName)
mqttc.connect(mqttServer, 1883, 60)
mqttc.on_connect = on_connect
mqttc.on_message = on_message

# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
mqttc.loop_forever()

print processName+" exiting"
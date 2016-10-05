<?php
include 'ip_in_range.php';

function controlThermostats($whichone,$command){
	$c = "status"; /* if command is empty, it'll just get status*/
	switch (TRUE){
	case ($command == "fanOn"):
		$c = "fan=on";
		break;
	case ($command == "fanAuto"):
		$c = "fan=auto";
		break;
	case ($command == "fanRecirc"):
		$c = "fan=recirc";
		break;
	case ($command == "modeCool"):
		$c="cool";
		break;
	case ($command == "modeHeat"):
		$c="heat";
		break;
	case ($command == "modeOff"):
		$c="off";
		break;
	case ($command == "tempUp"):
		$c="+";
		break;
	case ($command == "tempDown"):
		$c="-";
		break;
	case (!substr_compare($command,"temp=",0,5)):
		$split = array_map('trim',explode("=",$command));
		$c="temp=". $split[1];
		break;
	default:
		echo "Invalid Thermostat command<br />";
		return(false); /*Mess up in thermostat */
	}
	$response = file_get_contents("http://$whichone/$c");
	echo "Thermostat response: <br />";
	print_r($response);
	echo "<br />";
	return(true);
}

function ipControl($whichOne,$command){
    echo "<br />";
    echo "URL will be: $whichOne/$command<br />";
	$response = file_get_contents("http://$whichOne/$command");
	return(true);

};

if( !$_REQUEST["command"] ){
	echo "Didn't get a command";
	die();
}
/* First, check to see if control is allowed
   I check the incoming ip address, if it's not in house
   then maybe it has the secret word.  If not both of those,
   toss them out
*/
$ip = $_SERVER["REMOTE_ADDR"];
$ipok = ip_in_range($ip, '192.168.*.*');
echo $ip, ' in my house? ', ($ipok ? ' OK' : ' Fail'), "<br />";
$secret = isset($_REQUEST['secret'])?$_REQUEST['secret']:'jerk';
/*echo "Got: $secret<br />*/
$config = file_get_contents("/home/pi/.houserc");
$passwd = json_decode($config,true)["webpasswd"];
if (!$ipok && $passwd!=$secret){
	echo "Quit messing around<br />";
	die();
}
/*
    Suck the ip addresses for the various processes out 
    of the json string I got from the .houserc file.
    I put them here instead of each section to cut down on 
    typing and bugs.
*/
$Nthermo = json_decode($config,true)["Nthermostat"];
$Sthermo = json_decode($config,true)["Sthermostat"];
$houseMonitor = json_decode($config,true)['monitorhouse']['ipAddress'] .
                ':' . (json_decode($config,true)['monitorhouse']['port']);
$healthCheck = json_decode($config,true)['healthcheck']['ipAddress'] .
                ':' . (json_decode($config,true)['healthcheck']['port']);
$wemoControl = json_decode($config,true)['wemocontrol']['ipAddress'] .
                ':' . (json_decode($config,true)['wemocontrol']['port']);
                
# get the command I'm going to work with from the URL
$deviceAction = $_REQUEST['command'];
echo "Received device action: $deviceAction<br />";

$commandParts = explode(' ',$deviceAction);
switch ($commandParts[0]){
case "nthermo":
	#echo "case got nthermo<br />";
	controlThermostats($Nthermo,$commandParts[1]);
	break;
case "sthermo":
	#echo "case got sthermo<br />";
	controlThermostats($Sthermo,$commandParts[1]);
	break;
case "apump":
	#echo "case got apump<br />";
	$c = "AcidPump%20$commandParts[1]";
    ipControl("$houseMonitor", "pCommand?command=$c");
	break;
case "garage":
	#echo "case got garage<br />";
	$c = "Garage%20$commandParts[1]";
    ipControl("$houseMonitor", "pCommand?command=$c");
	break;
case "freezer":
	#echo "case got freezer<br />";
	$c = "Freezer%20$commandParts[1]";
    ipControl("$houseMonitor", "pCommand?command=$c");
	break;
case "pool":
	#echo "case got pool<br />";
	$c = "Pool%20$commandParts[1]";
    ipControl("$houseMonitor", "pCommand?command=$c");
	break;
case "preset":
	$c = "preset%20$commandParts[1]";
    ipControl("$houseMonitor", "pCommand?command=$c");
	break;
case "lights":
    $c = $commandParts[1];
    ipControl("$wemoControl", "pCommand?command=$c");
    break;
case "resetcommand":
	$c = "reset%20$commandParts[1]";
    ipControl("$healthCheck", "pCommand?command=$c");
	break;
default:
	echo "defaulted, invalid device";
	break;
}
?>

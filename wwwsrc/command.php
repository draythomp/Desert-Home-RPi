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
    echo "URL will be: $whichOne/$command";
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
$Nthermo = "192.168.0.202";
$Sthermo = "192.168.0.203"; 

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
	#echo "command is $commandParts[1]<br />";
	$mq = msg_get_queue(12);
	$c = "AcidPump, $commandParts[1]";
	if ( !msg_send($mq, 2, $c, true, true, $msg_err))
		echo "couldn't forward error: $msg_err<br />";
	break;
case "garage":
	#echo "case got garage<br />";
	#echo "command is $commandParts[1]<br />";
	$mq = msg_get_queue(12);
	$c = "Garage, $commandParts[1]";
	if ( !msg_send($mq, 2, $c, true, true, $msg_err))
		echo "couldn't forward error: $msg_err<br />";
	break;
case "pool":
	#echo "case got pool<br />";
	#echo "command is $commandParts[1]<br />";
	$mq = msg_get_queue(12);
	$c = "Pool, $commandParts[1]";
	if ( !msg_send($mq, 2, $c, true, true, $msg_err))
		echo "couldn't forward error: $msg_err<br />";
	break;
case "preset":
	$mq = msg_get_queue(12);
	$c = "preset, $commandParts[1]";
	if ( !msg_send($mq, 2, $c, true, true, $msg_err))
		echo "couldn't forward error: $msg_err<br />";
	break;
case "lights":
    $wemoIp = json_decode($config,true)["wemocontrol"]["ipAddress"];
    $wemoPort = json_decode($config,true)["wemocontrol"]["port"];
    $c = $commandParts[1];
    ipControl("$wemoIp:$wemoPort", "pCommand?command=$c");
    break;
/*  This is the old code that used the sys v message queue
	$mq = msg_get_queue(13);
	#echo "mq is $mq<br />";
	$c = $commandParts[1];
	#echo "command is $commandParts[1]<br />";
	if ( !msg_send($mq, 2, $c, true, true, $msg_err))
		echo "couldn't forward, error: $msg_err<br />";
	break;
    */
case "resetcommand":
	$mq = msg_get_queue(14);
	#echo "mq is $mq<br />";
	$c = "reset, $commandParts[1]";
	#echo "command is $c";
	if ( !msg_send($mq, 2, $c, true, true, $msg_err))
		echo "couldn't forward, error: $msg_err<br />";
	break;
default:
	echo "defaulted, invalid device";
	break;
}
?>

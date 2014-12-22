<?php
/* this is to allow cross domain data gathering 
   Not sure if I want people to be able to get to it
   directly, so this may disappear
*/
$request_headers = apache_request_headers();
if (isset($request_headers['Origin'])){
    $http_origin = $request_headers['Origin'];
    header("Access-Control-Allow-Origin: $http_origin");
}

define('IS_AJAX', isset($_SERVER['HTTP_X_REQUESTED_WITH']) && strtolower($_SERVER['HTTP_X_REQUESTED_WITH']) == 'xmlhttprequest');
$dbTimeout = 100;

/* if(!IS_AJAX){
	echo("Bug Off ");
	$ipaddress = $_SERVER["REMOTE_ADDR"];
	echo "Your IP is $ipaddress!";
	die();
}
 */
/*
Having everything happen on second boundaries can cause the 
database to be busy when all the processes fire at once. So, 
delaying a call when it is busy will keep database errors to 
a minimum.  Actually, the first delay will almost certainly 
assure the rest of them will execute just fine, since the 
second boundary will pass.
*/
function timedQuerySingle($statement){
	global $db, $dbTimeout;

	if ($db->busyTimeout($dbTimeout)){
		$result = $db->querySingle($statement);
		}
	else{
		error_log($statement);
		}
	$db->busyTimeout(0);
	return ($result);
	}
    
$config = file_get_contents("/home/pi/.houserc");
$dbName = json_decode($config,true)["database"];
$db= new SQLite3($dbName);
$dbTimeout = json_decode($config,true)["databaseLockDelay"];
    
# Get the various items out of the data base
# This could be one giant array() statement
# and actually save cpu , but getting them as
# variables first makes debugging and array 
# construction easier.  At least initially.
#$power = $db->querySingle("select rpower from power;");
$power = timedQuerySingle("select rpower from power;");
$outtemp = timedQuerySingle("select currenttemp from xbeetemp;");
# Current status of the two thermostats
$ntm = timedQuerySingle(
	'select status from thermostats where location="North";');
$stm = timedQuerySingle(
	'select status from thermostats where location="South";');
$ntt = timedQuerySingle(
	'select "temp-reading" from thermostats where location="North";');
$stt = timedQuerySingle(
	'select "temp-reading" from thermostats where location="South";');
# The North and South Thermostat setting (temp, mode, fan)
$ntms = timedQuerySingle(
	'select "s-mode" from thermostats where location="North";');
$stms = timedQuerySingle(
	'select "s-mode" from thermostats where location="South";');
$ntfs = timedQuerySingle(
	'select "s-fan" from thermostats where location="North";');
$stfs = timedQuerySingle(
	'select "s-fan" from thermostats where location="South";');
$ntts = timedQuerySingle(
	'select "s-temp" from thermostats where location="North";');
$stts = timedQuerySingle(
	'select "s-temp" from thermostats where location="South";');
$aps = timedQuerySingle(
	'select "status" from acidpump;');
$apl = timedQuerySingle(
	'select "level" from acidpump;');
$gd1 = timedQuerySingle(
	'select "door1" from garage;');
$gd2 = timedQuerySingle(
	'select "door2" from garage;');
$wh = timedQuerySingle(
	'select "waterh" from garage;');
$pm = timedQuerySingle(
	'select "motor" from pool;');
$pw = timedQuerySingle(
	'select "waterfall" from pool;');
$pl = timedQuerySingle(
	'select "light" from pool;');
$pf = timedQuerySingle(
	'select "fountain" from pool;');
$ps = timedQuerySingle(
	'select "solar" from pool;');
$pt = timedQuerySingle(
	'select "ptemp" from pool;');
$stl = timedQuerySingle(
	'select "level" from septic;');
$lfp = timedQuerySingle(
	'select "status" from "lights" where name="frontporch";');
$log = timedQuerySingle(
	'select "status" from "lights" where name="outsidegarage";');
$lcs = timedQuerySingle(
	'select "status" from "lights" where name="cactusspot";');
$lp = timedQuerySingle(
	'select "status" from "lights" where name="patio";');
$ws = timedQuerySingle(
	'select "json" from "weather";');
$mb = timedQuerySingle(
	'select "barometer" from "midnight";');
$db->close();
# The weather string is a pain, this is converting it, and
# since I can reuse variables and I'm tired of thinking up names
# I use the same name over and over again just to confuse
# anyone reading this.
# First, there an extra set of quotes around the string
$ws=substr($ws,1,strlen($ws)-2);
# Now I have to get rid of the \" that I had to use to put it in
# the database
$ws=str_replace("\\","",$ws);
#Now, convert the json into variables
$ws = json_decode($ws,true);
# Now, construct an array to use in the  json_encode()
# statement at the bottom.
$giveback = array('power' => $power, 'outsidetemp'=>$outtemp,
	'ntm'=>$ntm, 'stm'=>$stm, 'ntt'=>$ntt, 'stt'=>$stt,
	'ntms'=>$ntms, 'stms'=>$stms, 'ntfs'=>$ntfs, 'stfs'=>$stfs,
	'ntts'=>$ntts, 'stts'=>$stts,
	'aps'=>$aps, 'apl'=>$apl,
	'gd1'=>$gd1, 'gd2'=>$gd2, 'wh'=>$wh,
	'pm'=>$pm, 'pw'=>$pw, 'pl'=>$pl, 'pf'=>$pf, 'ps'=>$ps, 'pt'=>$pt,
	'stl'=>$stl,
	'lfp'=>$lfp, 'log'=>$log, 'lcs'=>$lcs, 'lp'=>$lp,
    'ws'=>$ws["windSpeed"]["WS"],'wd'=>$ws["windDirection"]["WD"],
    'hy'=>$ws["humidity"]["H"],'rtt'=>$ws["temperature"]["T"],
    'bp'=>$ws["barometer"]["BP"],'mb'=>$mb);
# And lastly, send it back to the web page
echo json_encode($giveback);
?>

<?php
/* this is to allow cross domain data gathering 
   Not sure if I want people to be able to get to it
   directly, so this may disappear
*/
/*
$request_headers = apache_request_headers();
if (isset($request_headers['Origin'])){
    $http_origin = $request_headers['Origin'];
    header("Access-Control-Allow-Origin: $http_origin");
}
*/

define('IS_AJAX', isset($_SERVER['HTTP_X_REQUESTED_WITH']) && strtolower($_SERVER['HTTP_X_REQUESTED_WITH']) == 'xmlhttprequest');
$dbTimeout = 100;

/* if(!IS_AJAX){
	echo("Bug Off ");
	$ipaddress = $_SERVER["REMOTE_ADDR"];
	echo "Your IP is $ipaddress!";
	die();
}
 */

function mysqlGetIt($statement, $conn){
    $result = mysql_query($statement, $conn);
    if (!$result){
        echo mysql_error($conn);
    }
    $row = mysql_fetch_array($result, MYSQL_BOTH);
    if (!$result){
        echo mysql_error($conn);
    }
    return ($row[0]);
}

#First, get the .houserc file for the parameters    
$config = file_get_contents("/home/pi/.houserc");

# The house database on the NAS
$hdbName = json_decode($config,true)["houseDatabase"];
$hdbHost = json_decode($config,true)["houseHost"];
$hdbPassword = json_decode($config,true)["housePassword"];
$hdbUser = json_decode($config,true)["houseUser"];
$hdb = mysql_connect($hdbHost,$hdbUser, $hdbPassword);
if (!$hdb){
    die('Unable to connect to database! ' . mysql_error());
}
mysql_select_db($hdbName, $hdb) or die('Unable to open database!' . mysql_error());

# Get the various items out of the data base
# This could be one giant array() statement
# and actually save cpu , but getting them as
# variables first makes debugging and array 
# construction easier.  At least initially.
$power = mysqlGetIt(
	"select rpower from power;", $hdb);
# Current status of the two thermostats
$ntm = mysqlGetIt(
	'select status from thermostats where location="North";', $hdb);
$stm = mysqlGetIt(
	'select status from thermostats where location="South";', $hdb);
$ntt = mysqlGetIt(
	'select `temp-reading` from thermostats where location="North";', $hdb);
$stt = mysqlGetIt(
	'select `temp-reading` from thermostats where location="South";', $hdb);
# The North and South Thermostat setting (temp, mode, fan)
$ntms = mysqlGetIt(
	'select `s-mode` from thermostats where location="North";', $hdb);
$stms = mysqlGetIt(
	'select `s-mode` from thermostats where location="South";', $hdb);
$ntfs = mysqlGetIt(
	'select `s-fan` from thermostats where location="North";', $hdb);
$stfs = mysqlGetIt(
	'select `s-fan` from thermostats where location="South";', $hdb);
$ntts = mysqlGetIt(
	'select `s-temp` from thermostats where location="North";', $hdb);
$stts = mysqlGetIt(
	'select `s-temp` from thermostats where location="South";', $hdb);
# Garage stuff
$gd1 = mysqlGetIt(
	'select door1 from garage;', $hdb);
$gd2 = mysqlGetIt(
	'select door2 from garage;', $hdb);
$wh = mysqlGetIt(
	'select waterh from garage;', $hdb);
# Pool stuff
$pm = mysqlGetIt(
	'select motor from pool;', $hdb);
$pw = mysqlGetIt(
	'select waterfall from pool;', $hdb);
$pl = mysqlGetIt(
	'select light from pool;', $hdb);
$pf = mysqlGetIt(
	'select fountain from pool;', $hdb);
$ps = mysqlGetIt(
	'select solar from pool;', $hdb);
$pt = mysqlGetIt(
	'select ptemp from pool;', $hdb);
# The septic tank level sensor
$stl = mysqlGetIt(
	'select level from septic;', $hdb);
    
# The house freezer defrost controller
$hft = mysqlGetIt(
    'select temperature from housefreezer where utime = (select max(utime) from housefreezer);',$hdb);
$hfd = mysqlGetIt(
    'select defroster from housefreezer where utime = (select max(utime) from housefreezer);',$hdb);
$hfmaxt = mysqlGetIt(
    'SELECT max(`temperature`)
    FROM `housefreezer`
    INNER JOIN (SELECT MAX(`timestamp`) as max FROM `housefreezer`) t ON TRUE
    WHERE `timestamp` >= (max - interval 1 day);', $hdb);
$hfmint = mysqlGetIt(
    'SELECT min(`temperature`)
    FROM `housefreezer`
    INNER JOIN (SELECT MAX(`timestamp`) as max FROM `housefreezer`) t ON TRUE
    WHERE `timestamp` >= (max - interval 1 day);', $hdb);
# The Wemo switches
$lfp = mysqlGetIt(
	'select status from wemo where name="frontporch";', $hdb);
$log = mysqlGetIt(
	'select status from wemo where name="outsidegarage";', $hdb);
$lcs = mysqlGetIt(
	'select status from wemo where name="cactusspot";', $hdb);
$lp = mysqlGetIt(
	'select status from wemo where name="patio";', $hdb);

# The weather is being handled by a different process on a 
# different machine. So, get the address and port number for
# an http get to gather the data
$stationIp = json_decode($config,true)["giveweather"]["ipAddress"];
$stationPort = json_decode($config,true)["giveweather"]["port"];
# Now go the data from the weather station
$response = file_get_contents("http://$stationIp:$stationPort/status");
# The $response variable has the json string returned.
# So, convert the json into variables
$ws = json_decode($response,true);
# Now, construct an array to use in the  json_encode()
# statement at the bottom.
# Starting with the data from house devices
$giveback = array('power' => $power, 
	'ntm'=>$ntm, 'stm'=>$stm, 'ntt'=>$ntt, 'stt'=>$stt,
	'ntms'=>$ntms, 'stms'=>$stms, 'ntfs'=>$ntfs, 'stfs'=>$stfs,
	'ntts'=>$ntts, 'stts'=>$stts,
	'gd1'=>$gd1, 'gd2'=>$gd2, 'wh'=>$wh,
	'pm'=>$pm, 'pw'=>$pw, 'pl'=>$pl, 'pf'=>$pf, 'ps'=>$ps, 'pt'=>$pt,
	'stl'=>$stl,
    'hft'=>$hft, 'hfd'=>$hfd,'hfmaxt'=>$hfmaxt, 'hfmint'=>$hfmint,
	'lfp'=>$lfp, 'log'=>$log, 'lcs'=>$lcs, 'lp'=>$lp,
    # The weather station data
    'outsidetemp'=>$ws["currentOutsideTemp"],
    'ws'=>$ws["windSpeed"],'wd'=>$ws["windDirectionC"],
    'hy'=>$ws["humidity"],'rtt'=>$ws["roofTemperature"],
    'bp'=>$ws["currentBarometric"],'mb'=>$ws["midnightBarometric"],
    'hws'=>$ws["maxWindSpeedToday"],'htt'=>$ws["maxTempToday"],
    'ltt'=>$ws["minTempToday"], 'rft'=>$ws["rainToday"]
    );
# And lastly, send it back to the web page
echo json_encode($giveback);
?>

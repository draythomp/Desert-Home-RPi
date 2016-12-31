<?php

define('IS_AJAX', isset($_SERVER['HTTP_X_REQUESTED_WITH']) && strtolower($_SERVER['HTTP_X_REQUESTED_WITH']) == 'xmlhttprequest');
$dbTimeout = 100;

/* if(!IS_AJAX){
	echo("Bug Off ");
	$ipaddress = $_SERVER["REMOTE_ADDR"];
	echo "Your IP is $ipaddress!";
	die();
}
 */

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

mysql_select_db($hdbName, $hdb) or die('Unable to open database!' . mysql_error());
#
# OK, got the database open and ready to use
#
$stuff = mysql_query(
	"SELECT name, temp, pvolt, rdate FROM `tempsensor` where rdate > date_sub(now(), interval 24 hour) ORDER BY `rdate`",
 $hdb);
if (!$stuff){
        echo mysql_error($conn);
}
$giveback = array();
while ($row = mysql_fetch_array($stuff, MYSQL_ASSOC)) {
    #printf("%s %s %s \n", $row["rdate"],$row["temp"],$row["pvolt"]);
    $giveback[$row["rdate"]] = array("name"=>$row["name"], "temp"=>$row["temp"],"volt"=>$row["pvolt"]);
}
#print_r ($giveback);
# And lastly, send it back to the web page
echo json_encode($giveback);
?>

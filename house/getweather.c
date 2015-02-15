/*
    Documentation at desert-home.com
    
    This is the actual weather module I run for controlling the house, as such, this 
    may not be what you want.  You may want other-stuff/weatherstation.c

    Experimentation with a USB interface to the Acu-Rite 5 in 1 Weatherstation
    specifically for the Raspberry Pi.  The code may work on other systems, but I 
    don't have one of those.  Contrary to other folk's thinking, I don't care if 
    this ever runs on a Windows PC or an Apple anything.
    
    I specifically used a model 2032 display with the 5 in 1 sensor that I picked
    up at one of those warehouse stores.  The display has a usb plug on it and 
    I thought it might be possible to read the usb port and massage the data myself.
    
    This code represents the result of that effort.
    
    I gathered ideas from all over the web.  I use the latest (for this second)
    libusb and about a thousand examples of various things that other people have 
    done and posted about.  Frankly, I simply can't remember all of them, so please,
    don't be offended if you see your ideas somewhere in here and it isn't attributed.
    
    I simply lost track of where I found what.
    
    This module relies on libusb version 1.0.19 which, at this time, can only be
    compiled from source on the raspberry pi.
    
    Because there's likely to be a version of libusb and the associated header file
    on a Pi, use the command line below to build it since the build of libusb-1.0.19
    places things in /usr/local
    
    cc -o weatherstation  weatherstation.c -L/usr/local/lib -lusb-1.0    
    use ldd weatherstation to check which libraries are linked in.
    If you still have trouble with compilation, remember that cc has a -v
    parameter that can help you unwind what is happening.
*/

#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#include <sys/time.h>
#include <libusb-1.0/libusb.h>

// The vendor id and product number for the AcuRite 5 in 1 weather head.
#define VENDOR 0x24c0
#define PRODUCT 0x0003

// I store things about the weather device USB connection here.
struct {
    libusb_device *device;
    libusb_device_handle *handle;
} weatherStation;
// These are the sensors the the 5 in 1 weather head provides
struct {
    float   windSpeed;
    time_t  wsTime;
    int     windDirection;
    time_t  wdTime;
    float   temperature;
    time_t  tTime;
    int     humidity;
    time_t  hTime;
    int     rainCounter;
    time_t  rcTime;
    float   barometer;
    time_t  bTime;
} weatherData;

// This is just a function prototype for the compiler
void closeUpAndLeave();

// I want to catch control-C and close down gracefully
void sig_handler(int signo)
{
  if (signo == SIGINT)
    fprintf(stderr,"Shutting down ...\n");
    closeUpAndLeave();
}

/*
This tiny thing simply takes the data and prints it so we can see it
*/
// Array to translate the integer direction provided to text
char *Direction[] = {
    "NW",  // 0   315
    "WSW", // 1   247.5
    "WNW", // 2   292.5
    "W",   // 3   270
    "NNW", // 4   337.5
    "SW",  // 5   225
    "N",   // 6   0
    "SSW", // 7   202.5
    "ENE", // 8   67.5
    "SE",  // 9   135
    "E",   // 10  90
    "ESE", // 11  112.5
    "NE",  // 12  45
    "SSE", // 13  157.5
    "NNE", // 14  22.5
    "S"  };// 15  180

// this is a bitmapped byte to tell if the various styles of reports have
// come in.  Bit 0 is R1 first type, bit 2 is R1 type 2 and bit 3 is R2
uint8_t reportsSeen = 0;

void showit(){

    // make sure enough reports have come in before reporting
    if( reportsSeen >= 7){  // Change this when report 3 is decoded
        fprintf(stdout, "{\"windSpeed\":{\"WS\":\"%.1f\",\"t\":\"%d\"},"
                        "\"windDirection\":{\"WD\":\"%s\",\"t\":\"%d\"},"
                        "\"temperature\":{\"T\":\"%.1f\",\"t\":\"%d\"},"
                        "\"humidity\":{\"H\":\"%d\",\"t\":\"%d\"},"
                        "\"rainCounter\":{\"RC\":\"%d\",\"t\":\"%d\"},"
                        "\"barometer\":{\"BP\":\"%4.1f\",\"t\":\"%d\"}}\n",
                weatherData.windSpeed, weatherData.wsTime,
                Direction[weatherData.windDirection],weatherData.wdTime,
                weatherData.temperature, weatherData.tTime,
                weatherData.humidity, weatherData.hTime,
                weatherData.rainCounter, weatherData.rcTime,
                weatherData.barometer, weatherData.bTime
                );
        fflush(stdout);
    }
}
/* 
This code translates the data from the 5 in 1 sensors to something 
that can be used by a human.
*/
int getWindSpeed(char *data){
    int leftSide = (data[3] & 0x1f) << 3;
    int rightSide = (data[4] & 0x70) >> 4;
    float speed = (leftSide | rightSide) / 2.0;
    return(speed);  
}

int getWindDirection(char *data){
    return(data[4] & 0x0f);
}
float getTemp(char *data){
    // This item spans bytes, have to reconstruct it
    int leftSide = (data[4] & 0x0f) << 7;
    int rightSide = data[5] & 0x7f;
    float combined = leftSide | rightSide;
    return((combined - 400) / 10.0);
}
int getHumidity(char *data){
    int howWet = data[6] &0x7f;
    return(howWet);
}
int getRainCount(char *data){

    int leftSide = (data[5] & 0x3F) << 7 ;
    int rightSide = data[6] & 0x7F;
    int count = leftSide | rightSide;
    return(count);
}
// Now that I have the data from the station, do something useful with it.

void decode(char *data, int length, int noisy){
    //int i;
    //for(i=0; i<length; i++){
    //    fprintf(stderr,"%0.2X ",data[i]);
    //}
    //fprintf(stderr,"\n"); */
    time_t seconds = time (NULL);
    //There are two varieties of data, both of them have wind speed
    // first variety of the data
    if ((data[2] & 0x0f) == 1){ // this has wind speed, direction and rainfall
        if(noisy)
            fprintf(stderr,"Wind Speed: %.1f ",getWindSpeed(data));
        weatherData.windSpeed = getWindSpeed(data);
        weatherData.wsTime = seconds;
        if(noisy)
            fprintf(stderr,"Wind Direction: %s ",Direction[getWindDirection(data)]);
        weatherData.wdTime = seconds;
        weatherData.windDirection = getWindDirection(data);
        if(noisy){
            fprintf(stderr,"Rain Counter: %d ",getRainCount(data));
            fprintf(stderr,"\n");
        }
        weatherData.rainCounter = getRainCount(data);
        weatherData.rcTime = seconds;
        reportsSeen |= 0x01; //I've seen report 1 type 2 now
    }
    // this is the other variety
    if ((data[2] & 0x0f) == 8){ // this has wind speed, temp and relative humidity
        if(noisy)
            fprintf(stderr,"Wind Speed: %.1f ",getWindSpeed(data));
        weatherData.windSpeed = getWindSpeed(data);
        weatherData.wsTime = seconds;
        if(noisy)
            fprintf(stderr,"Temperature: %.1f ",getTemp(data));
        weatherData.temperature = getTemp(data);
        weatherData.tTime = seconds;
        if(noisy){
            fprintf(stderr,"Humidity: %d ", getHumidity(data));
            fprintf(stderr,"\n");
        }
        weatherData.humidity = getHumidity(data);
        weatherData.hTime = seconds;
        reportsSeen |= 0x02;  // I've seen report 1 type 2 now

    }
}
/*
This code is related to dealing with the USB device
*/
// This searches the USB bus tree to find the device
int findDevice(libusb_device **devs)
{
    libusb_device *dev;
    int err = 0, i = 0, j = 0;
    uint8_t path[8]; 
    
    while ((dev = devs[i++]) != NULL) {
        struct libusb_device_descriptor desc;
        int r = libusb_get_device_descriptor(dev, &desc);
        if (r < 0) {
            fprintf(stderr,"Couldn't get device descriptor, %s\n", libusb_strerror(err));
            return(1);
        }

        fprintf(stderr,"%04x:%04x (bus %d, device %d)",
            desc.idVendor, desc.idProduct,
            libusb_get_bus_number(dev), libusb_get_device_address(dev));
        fprintf(stderr,"\n");
        if (desc.idVendor == VENDOR && desc.idProduct == PRODUCT){
            fprintf(stderr,"Found the weather station\n");
            weatherStation.device = dev;
            return (1);
        }
    }
    return(0);
}

// to handle testing and try to be clean about closing the USB device,
// I'll catch the signal and close off.
void closeUpAndLeave(){
    //OK, done with it, close off and let it go.
    fprintf(stderr,"Done with device, release and close it\n");
    int err = libusb_release_interface(weatherStation.handle, 0); //release the claimed interface
    if(err) {
        fprintf(stderr,"Couldn't release interface, %s\n", libusb_strerror(err));
    }
    fprintf(stderr, " Released interface and restored kernal driver\n");
    libusb_close(weatherStation.handle);
    fprintf(stderr, " Closed Weatherstation device\n");
    libusb_exit(NULL);
    fprintf(stderr, " Closed USB interface\n");
    exit(0);
}

// This is where I read the USB device to get the latest data.
unsigned char data[50]; // where we want the data to go
unsigned char oldR2[50] = "howdy";

int getit(int whichOne, int noisy){
    int actual; // how many bytes were actually read
    
    // The second parameter is bmRequestType and is a bitfield
    // See http://www.beyondlogic.org/usbnutshell/usb6.shtml
    // for the definitions of the various bits.  With libusb, the 
    // #defines for these are at:
    // http://libusb.sourceforge.net/api-1.0/group__misc.html#gga0b0933ae70744726cde11254c39fac91a20eca62c34d2d25be7e1776510184209

    actual = libusb_control_transfer(weatherStation.handle, 
        LIBUSB_REQUEST_TYPE_CLASS | LIBUSB_RECIPIENT_INTERFACE | LIBUSB_ENDPOINT_IN,
        //These bytes were stolen with a USB sniffer
        0x01,0x0100+whichOne,0,
        data, sizeof(data), 10000);
    if (actual < 0){
        fprintf(stderr,"Read didn't work for report %d, %s\n", whichOne, libusb_strerror(actual));
    }
    else {
        // If you want both of the reports that the station provides,
        // just allow for it.  Right this second, I've found every thing
        // I need in report 1.  When I look further at report 2, this will
        // change
        //fprintf(stderr,"R%d:%d:", whichOne, actual);
        //int i;
        //for(i=0; i<actual; i++){
        //    fprintf(stderr,"%0.2X ",data[i]);
        //}
        //fprintf(stderr,"\n");
        if (whichOne == 1){
            // The actual data starts after the first byte
            // The first byte is the report number returned by 
            // the usb read.
            decode(&data[1], actual-1, noisy);
        }
        if (whichOne == 2){
        // This is an experiment that will probably get removed
        // I'm trying to understand how the barometer on the 
        // AcuRite console works.  
            if (actual == 25)
            {
                // Don't bother with it unless it changes
                if (memcmp(oldR2, data, actual) != 0){
                    memcpy(oldR2, data, actual);
                    time_t seconds = time (NULL);
                    
                    float bar = 6.23 * (oldR2[23] << 8 | oldR2[24]) - 20402;
                    weatherData.barometer = bar / 100; // convert to mbar from pascals
                    weatherData.barometer += 81.1; //adjust for altitude
                    weatherData.bTime = seconds;
                    reportsSeen |= 0x04;  // I've seen report 2 now
                }
            }
        }
    }
}
// Find the device, and set up to read it periodically, then send 
// the data out stdout so another process can pick it up and do
// something reasonable with it.
// 
int main(int argc, char **argv)
{
    char *usage = {"usage: %s -u -n\n"};
    int libusbDebug = 0; //This will turn on the DEBUG for libusb
    int noisy = 0;       //This will print the packets as they come in
    libusb_device **devs;
    int r, err, c;
    ssize_t cnt;
    
    while ((c = getopt (argc, argv, "unh")) != -1)
        switch (c){
            case 'u':
                libusbDebug = 1;
                break;
            case 'n':
                noisy = 1;
                break;
            case 'h':
                fprintf(stderr, usage, argv[0]);
            case '?':
                exit(1);
            default:
                exit(1);
       }
    fprintf(stderr,"%s Starting ... ",argv[0]);
    fprintf(stderr,"libusbDebug = %d, noisy = %d\n", libusbDebug, noisy);
    // The Pi linker can give you fits.  If you get a linker error on
    // the next line, set LD_LIBRARY_PATH to /usr/local/lib 
    fprintf(stderr,"This is not an error!! Checking linker, %s\n", libusb_strerror(0));

    if (signal(SIGINT, sig_handler) == SIG_ERR)
        fprintf(stderr,"Couldn't set up signal handler\n"); 
    err = libusb_init(NULL);
    if (err < 0){
        fprintf(stderr,"Couldn't init usblib, %s\n", libusb_strerror(err));
        exit(1);
    }
    // This is where you can get debug output from libusb.
    // just set it to LIBUSB_LOG_LEVEL_DEBUG
    if (libusbDebug)
        libusb_set_debug(NULL, LIBUSB_LOG_LEVEL_DEBUG);
    else
        libusb_set_debug(NULL, LIBUSB_LOG_LEVEL_INFO);

    
    cnt = libusb_get_device_list(NULL, &devs);
    if (cnt < 0){
        fprintf(stderr,"Couldn't get device list, %s\n", libusb_strerror(err));
        exit(1);
    }
    // go get the device; the device handle is saved in weatherStation struct.
    if (!findDevice(devs)){
        fprintf(stderr,"Couldn't find the device\n");
        exit(1);
    }
    // Now I've found the weather station and can start to try stuff
    // So, I'll get the device descriptor
    struct libusb_device_descriptor deviceDesc;
    err = libusb_get_device_descriptor(weatherStation.device, &deviceDesc);
    if (err){
        fprintf(stderr,"Couldn't get device descriptor, %s\n", libusb_strerror(err));
        exit(1);
    }
    fprintf(stderr,"got the device descriptor back\n");
    
    // Open the device and save the handle in the weatherStation struct
    err = libusb_open(weatherStation.device, &weatherStation.handle);
    if (err){
        fprintf(stderr,"Open failed, %s\n", libusb_strerror(err));
        closeUpAndLeave();    }
    fprintf(stderr,"I was able to open it\n");
    // Now that it's opened, I can free the list of all devices
    libusb_free_device_list(devs, 1); // Documentation says to get rid of the list
                                      // Once I have the device I need
    fprintf(stderr,"Released the device list\n");
    err = libusb_set_auto_detach_kernel_driver(weatherStation.handle, 1);
    if(err){
        fprintf(stderr,"Some problem with detach %s\n", libusb_strerror(err));
        closeUpAndLeave();
    }
    int activeConfig;
    err =libusb_get_configuration(weatherStation.handle, &activeConfig);
    if (err){
        fprintf(stderr,"Can't get current active configuration, %s\n", libusb_strerror(err));;
        closeUpAndLeave();
    }
    fprintf(stderr,"Currently active configuration is %d\n", activeConfig);
    if(activeConfig != 1){
        err = libusb_set_configuration  (weatherStation.handle, 1);
        if (err){
            fprintf(stderr,"Cannot set configuration, %s\n", libusb_strerror(err));;
        closeUpAndLeave();
        }
        fprintf(stderr,"Just did the set configuration\n");
    }
    
    err = libusb_claim_interface(weatherStation.handle, 0); //claim interface 0 (the first) of device (mine had just 1)
    if(err) {
        fprintf(stderr,"Cannot claim interface, %s\n", libusb_strerror(err));
        closeUpAndLeave();
    }
    fprintf(stderr,"Claimed Interface\n");
    // I don't want to just hang up and read the reports as fast as I can, so
    // I'll space them out a bit.  It's weather, and it doesn't change very fast.
    sleep(1);
    fprintf(stderr,"Setting the device 'idle' before starting reads\n");
    err = libusb_control_transfer(weatherStation.handle, 
        0x21, 0x0a, 0, 0, 0, 0, 1000);
    sleep(1);
    int tickcounter= 0;
    fprintf(stderr,"Starting reads\n");
    while(1){
        sleep(1);
        if(tickcounter++ % 10 == 0){
            getit(1, noisy);
        }
        if(tickcounter % 30 == 0){
            getit(2, noisy);
        }
        if (tickcounter % 15 == 0){
            showit();
        }
    }
}
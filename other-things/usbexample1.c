/*
    Experimentation with a USB interface to the Acu-Rite 5 in 1 Weatherstation
    specifically for the Raspberry Pi.
    
    Because there likely to be a version of libusb and the associated header file
    on a Pi, use the command line below to build it since the build of libusb-1.0.19
    places things in /usr/local
    
    cc usbexample1.c -L/usr/local/lib -lusb-1.0    
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
    int verbose;
} weatherStation;

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

        //r = libusb_get_port_numbers(dev, path, sizeof(path));
        //if (r > 0) {
        //  fprintf(stderr," path: %d", path[0]);
        //  for (j = 1; j < r; j++)
        //      fprintf(stderr,".%d", path[j]);
        //}
        fprintf(stderr,"\n");
        
        if (desc.idVendor == VENDOR && desc.idProduct == PRODUCT){
            fprintf(stderr,"Found the one I want\n");
            weatherStation.device = dev;
            return (1);
        }
    }
    return(0);
}

// to handle testing and try to be clean about closing the USB device,
// I'll catch the signal and close off.

// I do several things here that aren't strictly necessary.  As I learned about
// libusb, I tried things and also used various techniques to learn about the 
// weatherstation's implementation.  I left a lot of it in here in case I needed to
// use it later.  Someone may find it useful to hack into some other device.
int main(void)
{
    libusb_device **devs;
    int r, err;
    ssize_t cnt;

    err = libusb_init(NULL);
    if (err < 0){
        fprintf(stderr,"Couldn't init usblib, %s\n", libusb_strerror(err));
        exit(1);
    }
    // This is where you can get debug output from libusb.
    // just set it to LIBUSB_LOG_LEVEL_DEBUG
    libusb_set_debug(NULL, LIBUSB_LOG_LEVEL_INFO);
    
    cnt = libusb_get_device_list(NULL, &devs);
    if (cnt < 0){
        fprintf(stderr,"Couldn't get device list, %s\n", libusb_strerror(err));
        exit(1);
    }
    // got get the device; the device handle is saved in weatherStation struct.
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
        exit(1);
    }
    fprintf(stderr,"I was able to open it\n");
    // Now that it's opened, I can free the list of all devices
    libusb_free_device_list(devs, 1); // Documentation says to get rid of the list
                                      // Once I have the device I need
    fprintf(stderr,"Released the device list\n");
    // Now I have to check to see if the kernal using udev has attached
    // a driver to the device.  If it has, it has to be detached so I can
    // use the device.
    if(libusb_kernel_driver_active(weatherStation.handle, 0) == 1) { //find out if kernel driver is attached
        fprintf(stderr,"Kernal driver active\n");
        if(libusb_detach_kernel_driver(weatherStation.handle, 0) == 0) //detach it
            fprintf(stderr,"Kernel Driver Detached!\n");
    }
    int activeConfig;
    err =libusb_get_configuration   (weatherStation.handle, &activeConfig);
    if (err){
        fprintf(stderr,"Can't get current active configuration, %s\n", libusb_strerror(err));;
        exit(1);
    }
    fprintf(stderr,"Currently active configuration is %d\n", activeConfig);

    err = libusb_set_configuration  (weatherStation.handle, 1);
    if (err){
        fprintf(stderr,"Cannot set configuration, %s\n", libusb_strerror(err));;
        exit(1);
    }
    fprintf(stderr,"Just did the set configuration\n");

    
    err = libusb_claim_interface(weatherStation.handle, 0); //claim interface 0 (the first) of device (mine had jsut 1)
    if(err) {
        fprintf(stderr,"Cannot claim interface, %s\n", libusb_strerror(err));
        exit(1);
    }
    fprintf(stderr,"Claimed Interface\n");
    fprintf(stderr,"Number of configurations: %d\n",deviceDesc.bNumConfigurations);
    struct libusb_config_descriptor *config;
    libusb_get_config_descriptor(weatherStation.device, 0, &config);
    fprintf(stderr,"Number of Interfaces: %d\n",(int)config->bNumInterfaces);
    // I know, the device only has one interface, but I wanted this code
    // to serve as a reference for some future hack into some other device,
    // so I put this loop to show the other interfaces that may
    // be there.  And, like most of this module, I stole the ideas from
    // somewhere, but I can't remember where (I guess it's google overload)
    const struct libusb_interface *inter;
    const struct libusb_interface_descriptor *interdesc;
    const struct libusb_endpoint_descriptor *epdesc;
    int i, j, k;
    for(i=0; i<(int)config->bNumInterfaces; i++) {
        inter = &config->interface[i];
        fprintf(stderr,"Number of alternate settings: %d\n", inter->num_altsetting);
        for(j=0; j < inter->num_altsetting; j++) {
            interdesc = &inter->altsetting[j];
            fprintf(stderr,"Interface Number: %d\n", (int)interdesc->bInterfaceNumber);
            fprintf(stderr,"Number of endpoints: %d\n", (int)interdesc->bNumEndpoints);
            for(k=0; k < (int)interdesc->bNumEndpoints; k++) {
                epdesc = &interdesc->endpoint[k];
                fprintf(stderr,"Descriptor Type: %d\n",(int)epdesc->bDescriptorType);
                fprintf(stderr,"Endpoint Address: 0x%0.2X\n",(int)epdesc->bEndpointAddress);
                // Below is how to tell which direction the 
                // endpoint is supposed to work.  It's the high order bit
                // in the endpoint address.  I guess they wanted to hide it.
                fprintf(stderr," Direction is ");
                if ((int)epdesc->bEndpointAddress & LIBUSB_ENDPOINT_IN != 0)
                    fprintf(stderr," In (device to host)");
                else
                    fprintf(stderr," Out (host to device)");
                fprintf(stderr,"\n");
            }
        }
    }
    //OK, done with it, close off and let it go.
    fprintf(stderr,"Done with device, release and close it\n");
    err = libusb_release_interface(weatherStation.handle, 0); //release the claimed interface
    if(err) {
        fprintf(stderr,"Couldn't release interface, %s\n", libusb_strerror(err));
        exit(1);
    }
    libusb_close(weatherStation.handle);
    libusb_exit(NULL);
    exit(0);
}
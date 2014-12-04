#include <stdio.h>
#include <stdlib.h>
#include <libusb-1.0/libusb.h>

//compile: gcc usbreset.c -o usbreset -lusb-1.0
//usage: ./usbreset 2 6
//use lsusb to check out the bus number and device number

struct libusb_device_handle *devh;
struct libusb_device *dev;
struct libusb_device **devs;

void resetUSB() {
    int success;
    int bpoint = 0;
    do {
        success = libusb_reset_device(devh);
        if ((bpoint % 10) == 0) {
            printf(".");
        }
        ++bpoint;
        if (bpoint > 100) {
            success = 1;
        }
    } while (success < 0);
    if (success) {
        printf("\nreset usb device failed:%d\n", success);
    } else {
        printf("\nreset usb device ok\n");
    }
}


struct libusb_device* search_device(int _busNum, int _devNum) { 
    libusb_device *l_dev;

    int i = 0;
    int l_busNum, l_devNum;
   
    while ((l_dev = devs[i++]) != NULL) {
        printf("check against %d device\n", i);
        l_busNum =(int) libusb_get_bus_number(l_dev);
        l_devNum =(int) libusb_get_device_address(l_dev);
        printf("bus number: %d; device number: %d\n", l_busNum, l_devNum);
        if ((l_busNum == _busNum) && (l_devNum == _devNum)) {
            printf("found device\n");
            return l_dev;
        }
    }
    return NULL;
}

int main(int argc, char **argv) {
    //parse the input parameters to get the bus number and device number
    int l_busNum, l_devNum;
    int l_ret;

    printf("program started!\n");
    if (argc < 3) {
        printf("not enough arguments!\n");
        printf("usage: ./usbreset <bus number> <dev number>\n");
        return 0;
    }
    printf("bus number: %s\n", argv[1]);
    printf("dev number: %s\n", argv[2]);
    l_busNum = atoi(argv[1]);
    l_devNum = atoi(argv[2]);
    printf("bus number: %d; dev number: %d\n", l_busNum, l_devNum);

    l_ret = libusb_init(NULL);
    if (l_ret < 0) {
        return l_ret;
    }
    l_ret = libusb_get_device_list(NULL, &devs);
    if (l_ret < 0) {
        return (int) l_ret;
    }
    dev = search_device(l_busNum, l_devNum);
    if (dev == NULL) {
        printf("device not found\n");
        return 0;
    }
    l_ret = libusb_open(dev, &devh);    
    if (l_ret == 0) {
        printf("got the usb handle successfully.\n");
    } else {
        printf("error getting usb handle.\n");
    }
    //reset the usb device
    resetUSB();
    //free the device list
    libusb_free_device_list(devs, 1);
    libusb_exit(NULL);
    return 0;
}

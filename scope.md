AutoDiskRepair Project
======================

Goal: The aim of this project is to automatically run through a complete repair of a broken 1TB Seagate disk drive by utilising several command line utilities.

Background: The heads on a 1TB Seagate Barracuda 1000 disk drive are failing, and it no longer works in its original Windows computer. I would like to run the ddrescue utility on it from Linux, but the disk can run successfully for about only 10 mins before it fails. However, turning it off then back on again can almost always reset it to allow for recovery to continue for another period.

Setup: There are multiple components that make up the repair environment:
1. The broken 1TB Seagate disk drive has a SATA interface, and is connected to:
2. A Digitech Computer XC4150 SATA/IDE to USB 2.0 Hard Drive Adaptor, which is powered from:
3. A 12V 2A power supply that is connected through:
4. A TP-Link Tapo P100 smart plug
5. A 4-port, powered Raspberry Pi USB3 Hub is connected to the above Digitech SATA USB adaptor, as well as:
6. A 2TB Seagate One Touch external USB drive.
7. A Raspberry Pi Zero 2 W is driving the above hub, and it is running Home Assistant to remotely control the Tapo P100 smart plug and has ddrescue installed.

Further details:
* The ddrescue util is intended to be used to read the broken 1TB Seagate disk drive sector by sector and create a disk image on the 2TB Seagate One Touch external USB drive.
* The 2TB Seagate One Touch external USB drive appears as /dev/sda1 and is mounted at /mnt/backup
* The recovery disk image produced is called lynnedisk.img. It already exists as a partial recovery so can continue to be used. Do not delete it.
* The 12V 2A power supply takes 10 seconds to completely power down.
* To successfully connect the hard disk through the SATA USB adaptor, the power should be turned on first, then after 10 seconds, the USB interface should be activated. However, it usually takes another 30 seconds or so for the broken drive to appear as a USB device.
* The lsblk command can be used to see which drive devices are connected.
* The lsusb command can be used to see which USB devices are connected.
* The "sudo dmesg --follow" command is very useful to see when the broken drive properly connects, so is available to begin data recovery, and also to see when it has failed and the data recovery should be halted.
* The first pass of the data recovery is done with the command "sudo ddrescue -d -r0 -n -c16 /dev/sdb /mnt/backup/lynnedisk.img /mnt/backup/mapfile.log" assuming that the broken drive appears as /dev/sdb
* Subsequent passes of the data recovery are done with the command "sudo ddrescue -d -r0 -c16 /dev/sdb /mnt/backup/lynnedisk.img /mnt/backup/mapfile.log"
* The recovery loop consists of: (i) power up the broken drive, (ii) 10 seconds later connect USB, (iii) when the broken drive appears in the dmesg log, start the ddrescue command refering to the right device, e.g. /dev/sdb, (iv) watch the dmesg log for drive failures, and at that point halt ddrescue, and power down the broken drive
* Logs should be taken of the whole process to allow for iteration and improvement of the automated repair project.

Complications:
* Both the broken 1TB Seagate SATA disk drive and the recovery 2TB Seagate One Touch external USB drive are connected through the same USB hub. If it is not possible to disconnect the USB for just the broken drive, it will be necessary to unmount the recovery drive and disconnect the whole USB hub, before reconnecting the hub and remounting the recovery drive.
* The broken drive can fail for a range of reasons, so monitoring of the dmesg log should be resilient to the appearance of multiple error messages. That said, dmesg is the source of truth, as the drive can have failed and yet still appear in lsusb or lsblk outputs.



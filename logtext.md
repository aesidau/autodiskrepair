# AutoDiskRepair — Text examples from logs and console commands

## example dmesg log when broken drive attaches as /dev/sdb
```
[ 1052.745926] usb 1-1.2: new high-speed USB device number 5 using dwc_otg
[ 1052.834778] usb 1-1.2: New USB device found, idVendor=152d, idProduct=2338, bcdDevice= 1.00
[ 1052.834820] usb 1-1.2: New USB device strings: Mfr=1, Product=2, SerialNumber=5
[ 1052.834842] usb 1-1.2: Product: USB to ATA/ATAPI bridge
[ 1052.834857] usb 1-1.2: Manufacturer: JMicron
[ 1052.834870] usb 1-1.2: SerialNumber: 000000000000
[ 1052.836246] usb-storage 1-1.2:1.0: USB Mass Storage device detected
[ 1052.838797] usb-storage 1-1.2:1.0: Quirks match for vid 152d pid 2338: 800000
[ 1052.839132] scsi host1: usb-storage 1-1.2:1.0
[ 1053.854587] scsi 1:0:0:0: Direct-Access     ST1000DM 003-1CH162            PQ: 0 ANSI: 5
[ 1053.855797] sd 1:0:0:0: Attached scsi generic sg1 type 0
[ 1053.880345] sd 1:0:0:0: [sdb] 1953525168 512-byte logical blocks: (1.00 TB/932 GiB)
[ 1053.880966] sd 1:0:0:0: [sdb] Write Protect is off
[ 1053.881006] sd 1:0:0:0: [sdb] Mode Sense: 28 00 00 00
[ 1053.881541] sd 1:0:0:0: [sdb] No Caching mode page found
[ 1053.881570] sd 1:0:0:0: [sdb] Assuming drive cache: write through
[ 1053.918685]  sdb: sdb1 sdb2 sdb3
[ 1053.919709] sd 1:0:0:0: [sdb] Attached SCSI disk
```
## example 1 of dmesg log when broken drive stops working
```
[ 2110.727933] usb 1-1.2: reset high-speed USB device number 5 using dwc_otg
[ 2141.248169] usb 1-1.2: reset high-speed USB device number 5 using dwc_otg
[ 2156.864689] sd 1:0:0:0: Device offlined - not ready after error recovery
[ 2156.864801] usb 1-1.2: USB disconnect, device number 5
[ 2156.865205] sd 1:0:0:0: [sdb] tag#0 UNKNOWN(0x2003) Result: hostbyte=0x05 driverbyte=DRIVER_OK cmd_age=77s
[ 2156.865233] sd 1:0:0:0: [sdb] tag#0 CDB: opcode=0x28 28 00 04 70 45 d8 00 00 01 00
[ 2156.865249] I/O error, dev sdb, sector 74466776 op 0x0:(READ) flags 0x800 phys_seg 1 prio class 2
```
## example 2 of dmesg log when broken drive stops working
```
[ 3044.415124] usb 1-1.2: reset high-speed USB device number 6 using dwc_otg
[ 3075.139192] usb 1-1.2: reset high-speed USB device number 6 using dwc_otg
[ 3090.767657] sd 1:0:0:0: Device offlined - not ready after error recovery
[ 3090.767742] sd 1:0:0:0: [sdb] tag#0 UNKNOWN(0x2003) Result: hostbyte=0x05 driverbyte=DRIVER_OK cmd_age=76s
[ 3090.767767] sd 1:0:0:0: [sdb] tag#0 CDB: opcode=0x28 28 00 04 7d ba f0 00 00 01 00
[ 3090.767766] usb 1-1.2: USB disconnect, device number 6
[ 3090.767784] I/O error, dev sdb, sector 75348720 op 0x0:(READ) flags 0x800 phys_seg 1 prio class 2
```
## example 3 of dmesg log when broken drive stops working
```
[ 1077.198968] sd 1:0:0:0: [sdb] Unaligned partial completion (resid=136, sector_sz=512)
[ 1077.199046] sd 1:0:0:0: [sdb] tag#0 CDB: opcode=0x28 28 00 00 04 cc 00 00 00 80 00
[ 1077.199109] sd 1:0:0:0: [sdb] tag#0 UNKNOWN(0x2003) Result: hostbyte=0x07 driverbyte=DRIVER_OK cmd_age=4s
[ 1077.199145] sd 1:0:0:0: [sdb] tag#0 CDB: opcode=0x28 28 00 00 04 cc 00 00 00 80 00
[ 1077.199170] I/O error, dev sdb, sector 314368 op 0x0:(READ) flags 0x800 phys_seg 16 prio class 2
[ 1092.380320] WARN::dwc_otg_hcd_urb_dequeue:639: Timed out waiting for FSM NP transfer to complete on 7
[ 1093.067936] usb 1-1.1: USB disconnect, device number 5
```
## example 4 of dmesg log when broken drive stops working
```
[15073.875732] I/O error, dev sdb, sector 1953393792 op 0x0:(READ) flags 0x800 phys_seg 2 prio class 2
[15073.875883] I/O error, dev sdb, sector 1953393808 op 0x0:(READ) flags 0x800 phys_seg 2 prio class 2
[15073.876037] I/O error, dev sdb, sector 1953393824 op 0x0:(READ) flags 0x800 phys_seg 2 prio class 2
```
## output of lsblk with broken drive as /dev/sdb
```
NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda           8:0    0   1.8T  0 disk
└─sda1        8:1    0   1.8T  0 part /mnt/backup
sdb           8:16   0 931.5G  0 disk
├─sdb1        8:17   0   100M  0 part
├─sdb2        8:18   0   931G  0 part
└─sdb3        8:19   0   450M  0 part
mmcblk0     179:0    0  59.5G  0 disk
├─mmcblk0p1 179:1    0   512M  0 part /boot/firmware
└─mmcblk0p2 179:2    0    59G  0 part /
```
## output of lsusb with drive connected through SATA USB bridge
```
Bus 001 Device 003: ID 0bc2:ab79 Seagate RSS LLC One Touch w/PW
Bus 001 Device 004: ID 152d:2338 JMicron Technology Corp. / JMicron USA Technology Corp. JM20337 Hi-Speed USB to SATA & PATA Combo Bridge
Bus 001 Device 002: ID 2e8a:000d Raspberry Pi USB3 HUB
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
```
## live output of ddrescue while performing a recovery on broken drive
```
GNU ddrescue 1.27
Press Ctrl-C to interrupt
Initial status (read from mapfile)
rescued: 3289 MB, tried: 996915 MB, bad-sector: 34244 MB, bad areas: 11

Current status
     ipos:   37753 MB, non-trimmed:        0 B,  current rate:    697 kB/s
     opos:   37753 MB, non-scraped:  962451 MB,  average rate:    543 kB/s
non-tried:        0 B,  bad-sector:   34244 MB,    error rate:       0 B/s
  rescued:    3508 MB,   bad areas:       11,        run time:      6m 44s
pct rescued:    0.35%, read errors:        0,  remaining time: 14d  1h 11m
                              time since last successful read:          0s
Scraping failed blocks... (forwards)
```

''' 
Filename: config.py
Author: CANQuest Team
Version: 1.0prod
Description: Configuration file for the CANQuest Backend Server. This file contains global variables and settings used throughout the server code.
'''
import threading
import time

# Global variables
wiper_status = 0x00
status_lock = threading.Lock()
verbose = False
client_sock = None
server_socket = None
stop_can = threading.Event()
server_down = False
ota_flash_status = 0x00
ota_flash_attempts = 0x00
start_time = time.time()
ota_complete = False
'''
Filename: can_handler.py
Author: CANQuest Team
Version: 1.0prod
Description: CAN Handler module for the CANQuest Backend Server. This module handles CAN bus initialization, message sending and receiving, and ECU management.
'''
import sys
import can
import time
import server.config as config
from ecus.ecm import ECM
from ecus.bcm import BCM  
from ecus.dcu import DCU
from ecus.tcu import TCU
from ecus.ivi import IVI
        
class CAN_Handler:
    '''Class to handle CANbus initialization, message sending and recieving, ECU additions. Creates instance of type can_handler.'''
    def __init__(self, interface='socketcan', channel='vcan0', bitrate=500000, verbose=config.verbose):
        '''
        Function to initialize the CAN_Handler class.
        Arguments:
        - interface: CAN interface type (default is 'socketcan').
        - channel: CAN channel (default is 'vcan0').
        - bitrate: CAN bus bitrate (default is 500000).
        - verbose: boolean flag to enable verbose output (default is False), taken from config.py
        '''
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.bus = None
        self.ecus = {}
        self._initialize_ecus()
        self.verbose = verbose

    def setup(self):
        '''Function to initialize the CANbus interface.'''
        try:
            print(f"Setting up CAN interface {self.channel}...")
            self.bus = can.interface.Bus(interface=self.interface, channel=self.channel, bitrate=self.bitrate)
        except OSError as e:
            print(f"Error setting up CAN interface: {e}")
            sys.exit(1)

    def send_msg(self, can_id, data, is_multiframe=False, is_extended_id=False, is_status=False):
        '''
        Function to send a standard-length message on the CANbus.
        Arguments:
        - can_id: TX arbitration CAN ID of the message.
        - data: Data to be sent in the message.
        - is_multiframe: Boolean flag to indicate if the message is a multi-frame message (default is False).
        - is_extended_id: Boolean flag to indicate if the message uses extended ID (default is False).
        - is_status: Boolean flag to indicate if the message is a status message (default is False).
        '''
        try:
            if is_multiframe is True: #if multiframe message, pass to send_multiframe_msg
                self.send_multiframe_msg(can_id, data, is_extended_id)
                return
            if is_status is True: #send status messages without DLC as regular CAN messages
                message = can.Message(arbitration_id=can_id, data=data, is_extended_id=is_extended_id)
                self.bus.send(message)
                return
            #calculate Data Length Code (DLC) for diagnostic messages and send over interface
            dlc = len(data)
            final_data = []
            final_data = [dlc] + data
            message = can.Message(arbitration_id=can_id, data=final_data, is_extended_id=is_extended_id)
            self.bus.send(message)
            if (self.verbose): print(f"Sent message: {message}")
        except can.CanError:
            print("MESSAGE NOT SENT")

    def send_multiframe_msg(self, can_id, data, is_extended_id=False):
        '''
        Function to send a multi-frame message on the CANbus.
        Arguments:
        - can_id: TX arbitration CAN ID of the message.
        - data: Data to be sent in the message.
        - is_extended_id: Boolean flag to indicate if the message uses extended ID (default is False).
        '''
        try:
            dlc = len(data)
            updated_data = [dlc] + data
            #break into frames of 7 bytes (+1 for DLC)
            frame_size = 7
            num_frames = (len(updated_data)  + (frame_size - 1)) // frame_size
            btf_sequences = [0x10, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27]
            for f in range(0, num_frames):
                btf = btf_sequences[f]
                frame = updated_data[f*frame_size:(f+1)*frame_size]
                final_frame = [btf] + frame
                message = can.Message(arbitration_id=can_id, data=final_frame, is_extended_id=is_extended_id)
                self.bus.send(message)
                if (self.verbose): print(f"Sent message: {message}")
        except can.CanError:
            print("MESSAGE NOT SENT")
    
    def handle_multiframe_msg(self, first_msg):
        total_len = first_msg.data[1]
        payload = list(first_msg.data[2:])
        expected_sn = 1
        while len(payload) < total_len:
            next_msg = self.bus.recv(timeout=30.0)
            if next_msg is None:
                print('Timeout while waiting for consecutive frame! Try again...')
                self.bus.send(can.Message(arbitration_id=first_msg.arbitration_id+8, data=[0x7F, first_msg.data[2], 0x22], is_extended_id=False))
                return
            if next_msg.arbitration_id != first_msg.arbitration_id:
                continue
            sn = next_msg.data[0] & 0x0F
            if next_msg.data[0] >> 4 != 0x2 or sn != expected_sn:
                print("Unexpected Sequence Number Error. Resend.")
                self.bus.send(can.Message(arbitration_id=first_msg.arbitration_id+8, data=[0x7F, first_msg.data[2], 0x22], is_extended_id=False))
                return
            payload.extend(next_msg.data[1:])
            expected_sn = (expected_sn+1)%16
        return ' '.join(f'{byte:02x}' for byte in payload[:total_len])

    def recv_msg(self):
        '''Function to recieve a message on the CANbus. Actively listens through initialization.'''
        try:
            message = self.bus.recv()
            if (self.verbose): print(f"Received message: {message}")
            if message.data[0] == 0x10:
                if (self.verbose): print("handling multiframe...")
                #maybe add flow control later
                self.bus.send(can.Message(arbitration_id=message.arbitration_id+8, data=[0x30, 0x00, 0x00], is_extended_id=False))
                complete_payload = self.handle_multiframe_msg(message)
                if complete_payload is not None:
                    ecu = self.get_ecu(message.arbitration_id)
                    if ecu:
                        ecu.handle_request(complete_payload, self, multiframe=True)
                    else:
                        if self.verbose: print("ECU not found") 
                        return
                return message, complete_payload
            else:
                #parse the message and extract the payload
                parsed = '{0:f} {1:x} {2:x} '.format(message.timestamp, message.arbitration_id, message.dlc)
                payload = ''
                for i in range(message.dlc):
                    payload += '{:02x} '.format(message.data[i])

                #map the ecu based on the TX arbitration ID (request)
                ecu = self.get_ecu(message.arbitration_id)
                if ecu:
                    ecu.handle_request(payload, self)
                else:
                    if self.verbose: print("ECU not found")
                    return
                return message, payload
        
        except can.CanError:
            print("MESSAGE NOT RECEIVED")

    def shutdown(self):
        '''Function to close the CANbus interface.'''
        print("Shutting down CAN interface...")
        if self.bus:
            if config.client_sock:
                config.client_sock.sendall("-1".encode('utf-8')) 
            self.bus.shutdown()
    
    def _initialize_ecus(self):
        '''Function to map the arbitration ID to the corresponding ECU.'''

        #TODO: add your own ECU mapping here in the key: value pair format, ECU_REQUEST_ARB_ID: [ECU_NAME, ECU_RESPONSE_ARB_ID]
        ecu_dict = {
                0x123: ['ECM', 0x321], 
                0x456: ['BCM', 0x654], 
                0x789: ['DCU', 0x7FF],
                0x7A8: ['TCU', 0x7B0],
                0x7D0: ['IVI', 0x7D8]
                }
                #tcu will be 7A0/7A8 or 7A8/7B0 pair (fun twist on 1960 from flintstones)

        
        #TODO: add your own ECU initialization here, make sure to import custom class at the top as well
        for req_arb_id, (name, rsp_arb_id) in ecu_dict.items():
            if name == "ECM":
                self.ecus[req_arb_id] = ECM(name, req_arb_id, rsp_arb_id, verbose=config.verbose)
            elif name == "BCM":
                self.ecus[req_arb_id] = BCM(name, req_arb_id, rsp_arb_id, verbose=config.verbose)
            elif name == "DCU":
                self.ecus[req_arb_id] = DCU(name, req_arb_id, rsp_arb_id, verbose=config.verbose)
            elif name == "TCU":
                self.ecus[req_arb_id] = TCU(name, req_arb_id, rsp_arb_id, verbose=config.verbose)

    def _init_ivi(self):
        if config.ota_complete == True and 0x7D0 not in self.ecus:
            if config.verbose: print("initializing IVI\n")
            self.ecus[0x7D0] = IVI(IVI, 0x7D0, 0x7D8, verbose=config.verbose)
            self.broadcast_ivi_boot(is_init=True)

    
    def get_ecu(self,arb_id):
        '''Helper function to return request arbitration ID of the ECU.'''
        return self.ecus.get(arb_id)
    
    def broadcast_wiper_data(self):
        '''Function to broadcast wiper data on the CANbus. This function runs in a separate thread. Can disable if desired.'''
        while not config.stop_can.is_set():
            with config.status_lock:
                stat_msg = [config.wiper_status, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            self.send_msg(0x058, stat_msg, is_status=True)
            time.sleep(0.1)
        
    def broadcast_tcu_data(self):
        current_time = (int(time.time() - config.start_time))
        timestamp = current_time.to_bytes(2, 'big')
        if config.ota_flash_status == 0x01:
            ascii_stat = [0x46, 0x41, 0x49, 0x4C]
        elif config.ota_flash_status == 0x02:
            ascii_stat = [0x49, 0x4E, 0x50, 0x52]
        elif config.ota_flash_status == 0x03:
            ascii_stat = [0x47, 0x4F, 0x4F, 0x44]
        else:
            ascii_stat = [0x49, 0x44, 0x4B, 0x3F]
        tcu_msg = [timestamp[0], timestamp[1], config.ota_flash_attempts, config.ota_flash_status, ascii_stat[0], ascii_stat[1], ascii_stat[2], ascii_stat[3]]
        #stat msg: ID # timestamp flash attempt result (success/fail), # flash attempt (ctr), maybe sub-code/crc check???, 
        self.send_msg(0x333, tcu_msg, is_status=True)
    
    def broadcast_ivi_boot(self, is_init=False):
        IVI = self.get_ecu(0x7D0)
        time_since_boot = int(time.time() - IVI.boot_time)
        timestamp = time_since_boot.to_bytes(2, 'big')
        full_msg = b''
        if is_init:
            full_msg += b'OTA FLASH SUCCESS\n'
            full_msg += b'-----FLINTFOTAINMENT SYSTEM BOOT-----\n'
            full_msg += b'DEBUG MODE AVAILABLE WITH EXTENDED, INITIALIZING AT 0x7D0...\n'
        if IVI.debug != IVI.flags['debug']:
            full_msg += b'ENTERING DEBUG MODE....'
            IVI.flags['debug'] = IVI.debug
        if IVI.algo != IVI.flags['algo']: 
            full_msg += b'LOADING XOR ALGORITHM...\n'
            IVI.flags['algo'] = IVI.algo
        if IVI.mem != IVI.flags['mem']: 
            full_msg += b'PARSING CONFIGURABLE MEMORY 0x574253...\n'
            full_msg += b'WRITE CONDITION = NUM(YEARS_CURRENT) - NUM(YEARS_FLINTSTONES)...\n'
            IVI.flags['mem'] = IVI.mem
        if IVI.boot_stat != IVI.flags['stat']: 
            full_msg += b'-----BOOT COMPLETE!-----'
            full_msg+= b'flag{fl1ntst0n3s_1n_f3d0r@s}'
            IVI.flags['stat'] = IVI.boot_stat
        chunks = [full_msg[i:i+5] for i in range(0, len(full_msg), 5)]

        for index, chunk in enumerate(chunks):
            data = list(timestamp) + [index] + list(chunk)
            #data += [0x00] * (8 - len(data))
            self.send_msg(0x313, data, is_status=True)
    
    def send_uds_ota(self):
        TCU = self.get_ecu(0x7A8)
        TCU.send_ota_data(self)
    
    def process_client_data(self, data):
        if "0x0E" in data: #wipers on
            if config.verbose: print("WIPERS ON")
            config.wiper_status = 0x01
        elif "0x0F" in data: #wipers off
            if config.verbose: print("WIPERS OFF")
            config.wiper_status = 0x00
        elif "0x10" in data: #OTA update attempt
            #0x00 = regular???, 0x01 = fail, 0x02 = in progress, 0x03 = success
            config.ota_flash_attempts += 1
            config.ota_flash_status = 0x02
            self.broadcast_tcu_data() #broadcasts the in progress first
            self.send_uds_ota()
            if config.verbose: print("Flash attempt ctr: ", config.ota_flash_attempts)
            config.ota_flash_status = 0x01
            time.sleep(1)
            config.client_sock.sendall("0x13".encode('utf-8'))
            self.broadcast_tcu_data()
        else:
            return
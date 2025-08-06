'''
Filename: ivi.py
Author: CANQuest Team
Version: 1.0prod
Description: Custom In-Vehicle Infotainment (IVI) class used for CHV. Inherits from the ECU class.
'''
import time
import re
import random
from .ecu import ECU
from services.uds_services import *
import server.config as config

class IVI(ECU):
    def __init__(self, name, req_arb_id, rsp_arb_id, verbose=config.verbose):
        super().__init__(name, req_arb_id, rsp_arb_id, verbose=config.verbose)
        self.unlocked = False
        self.seed = []
        self.stored_key = []
        self.boot_time = time.time()

        #flags for status messages
        self.debug = False
        self.algo = False
        self.mem = False
        self.boot_stat = False

    def initialize_services(self):
        return {
            0x10: DiagnosticSessionControl(),
            0x27: SecurityAccess(),
            0x3D: WriteMemoryByAddress(),
        }

    def security_algorithm(self, rsp):
        seed = []
        for i in range(0,3):
            seed_val = random.randint(0,255)
            seed.append(seed_val)
            rsp.append(seed_val)
        if(self.verbose): print("generated seed", seed)
        self.seed = seed
        key = [(seed_val ^ 0xFF) for seed_val in seed]
        if (self.verbose): print("stored key: ", key)
        hex_key = [hex(key_byte) for key_byte in key]
        if (self.verbose): print("hex key: ", hex_key)
        self.stored_key = key
        return rsp

    def handle_request(self, payload, cansend, verbose=False, multiframe=False):
        print("tbd")
        if (self.verbose): print(len(payload))
        payload_bytes = re.split(r'\s+', payload)
        dlc = payload_bytes[0]
        service_id = int(payload_bytes[1], 16)
        if (self.verbose): print(service_id)
        service=self.get_service(service_id)
        if service is None:
            cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x11])
            return
        elif service.validate_length(dlc, payload_bytes) is False:
            cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x13])
            return
        if isinstance(service, DiagnosticSessionControl):
            self.active_session = service.get_diagnostic_session(payload_bytes, trigger=True)
            if (self.verbose): print("Active session is:", self.active_session)
        rsp = service.construct_msg(payload_bytes, key=self.stored_key)
        if (self.verbose): print(rsp)
        if self.active_session == 0x03 or isinstance(service, DiagnosticSessionControl):
            if self.active_session == 0x03 and isinstance(service, DiagnosticSessionControl):
                self.debug = True
                cansend.broadcast_ivi_boot()
            if (self.verbose): print("worked")
            if rsp == [0x67, 0x01]:
                if (self.verbose): print("security success yuh")
                new_rsp = self.security_algorithm(rsp)
                cansend.send_msg(self.rsp_arb_id, new_rsp)
                self.algo = True
                cansend.broadcast_ivi_boot()
            elif rsp == [0x67, 0x02]:
                if (self.verbose): print("validated seed, successful unlock")
                cansend.send_msg(self.rsp_arb_id, rsp)
                self.unlocked = True
                self.mem = True
                cansend.broadcast_ivi_boot()
            elif isinstance(service, WriteMemoryByAddress):
                if self.unlocked == True:
                    if rsp == [0x7D, 0x13, 0x57, 0x42, 0x53, 0x01]:
                        if (self.verbose): print("success yuh")
                        cansend.send_msg(self.rsp_arb_id, rsp)
                        if config.client_sock:
                            config.client_sock.sendall("0x11".encode('utf-8'))
                            config.client_sock.sendall("0x04".encode('utf-8'))
                        self.boot_stat = True
                        cansend.broadcast_ivi_boot()
                    else:
                        cansend.send_msg(self.rsp_arb_id, rsp)
                else:
                    cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x33])

            else:
                cansend.send_msg(self.rsp_arb_id, rsp)
        else:
            cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x7F])
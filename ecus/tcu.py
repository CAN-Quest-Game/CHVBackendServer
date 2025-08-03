'''
Filename: tcu.py
Author: CANQuest Team
Version: 1.0prod
Description: Custom Telematics Control Module (TCU) class used for CHV. Inherits from the ECU class.
'''
import re
import time
from .ecu import ECU
from services.uds_services import *
import server.config as config

class TCU(ECU):
    def __init__(self, name, req_arb_id, rsp_arb_id, verbose=config.verbose):
        super().__init__(name, req_arb_id, rsp_arb_id, verbose=config.verbose)

    def initialize_services(self):
        return {
            0x10: DiagnosticSessionControl(),
            0x3E: TesterPresent(),
            0x34: RequestDownload()
        }

    def send_ota_data(self, cansend):
        #send 0x34, 0x36
        #accept ^ in init services 0x35
        # if config.ota_flash_status == 0x02:
        #     print("working TCU")

        #currently set memory size (amt bytes transferred) to 21h = 33 bytes
        req_download = [0x34, 0x00, 0x13, 0x43, 0x48, 0x56, 0x21]
        cansend.send_msg(self.req_arb_id, req_download)
        msg = '07 ' + ' '.join(f'{byte:02X}' for byte in req_download)
        print(msg)
        self.handle_request(msg, cansend)
       
        transfer_1 = [0x36, 0x01, ]
        transfer_2 = [0x36, 0x02]
        transfer_3 = [0x36, 0x03]
        cansend.send_msg(self.req_arb_id, transfer_data)
        
        req_exit = [0x37]
        cansend.send_msg(self.req_arb_id, req_exit)

       # self.rsp_arb_id()
        #cansend.send_msg(self.req_arb_id, [0x34, 0xDE, 0xAD, 0xBE, 0xEF])

    def handle_request(self, payload, cansend, verbose=False):
        if (verbose): print(len(payload))
        payload_bytes = re.split(r'\s+', payload)
        dlc = payload_bytes[0]
        service_id = int(payload_bytes[1], 16)
        if (verbose): print(service_id)
        service=self.get_service(service_id)
        
        if service is None:
            cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x11])
            return
        elif service.validate_length(dlc, payload_bytes) is False:
            cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x13])
            return

        if isinstance(service, RequestDownload):
            print("TBD")
            #change to respond to B as 3 blocks of 11 bytes
            cansend.send_msg(self.rsp_arb_id, [0x74, 0x10, 0x0B])

        else:
            cansend.send_msg(self.rsp_arb_id, rsp)
'''
Filename: tcu.py
Author: CANQuest Team
Version: 1.0prod
Description: Custom Telematics Control Module (TCU) class used for CHV. Inherits from the ECU class.
'''
import re
import time
import binascii
from .ecu import ECU
from services.uds_services import *
import server.config as config

class TCU(ECU):
    def __init__(self, name, req_arb_id, rsp_arb_id, verbose=config.verbose):
        super().__init__(name, req_arb_id, rsp_arb_id, verbose=config.verbose)
        self.req_download_complete = False
        self.sequence = 0x00
        self.valid_crc = False

    def initialize_services(self):
        return {
            0x10: DiagnosticSessionControl(),
            0x34: RequestDownload(),
            0x36: TransferData(),
            0x37: RequestTransferExit()
        }


    def send_ota_data(self, cansend):
        #send 0x34, 0x36
        # if config.ota_flash_status == 0x02:
        #     print("working TCU")

        #CORRUPTPAYLOAD: 53 4F 46 54 57 41 52 45 2D 55 50 44 41 54 45 3A 20 59 61 62 62 61 2D 64 61 62 62 79 2D 64 6F 6F 21
        #EXPECTEDPAYLOAD: 53 4F 46 54 57 41 52 45 2D 55 50 44 41 54 45 3A 20 59 61 62 62 61 2D 64 61 62 62 61 2D 64 6F 6F 21

        #start programming session
        cansend.send_msg(self.req_arb_id, [0x10, 0x02])
        cansend.send_msg(self.rsp_arb_id, [0x50, 0x02])

        #request download
        #currently set memory size (amt bytes transferred) to 2E = 46 bytes, 3 chunks of 11 (0Bh)
        req_download = [0x34, 0x00, 0x13, 0x43, 0x48, 0x56, 0x2E]
        cansend.send_msg(self.req_arb_id, req_download)
        cansend.send_msg(self.rsp_arb_id, [0x74, 0x10, 0x0B])

        #define OTA
        #TODO: change header to also be 11 bytes?
        header = [0x36, 0x01, 0x48, 0x45, 0x41, 0x44, 0x03, 0x00, 0x21, 0x07, 0xD0]
       # header = magic # (4), version (1), payload size (2) - 21h bytes = 33d, target ecu id(2), 
       #ECU ID FOR radio = 7D0 (2000s flintstone movie came out!!)
        b1 = [0x36, 0x02, 0x53, 0x4F, 0x46, 0x54, 0x57, 0x41, 0x52, 0x45, 0x2D, 0x55, 0x50]
        b2 = [0x36, 0x03, 0x44, 0x41, 0x54, 0x45, 0x3A, 0x20, 0x59, 0x61, 0x62, 0x62, 0x61]
        b3 = [0x36, 0x04, 0x2D, 0x64, 0x61, 0x62, 0x62, 0x79, 0x2D, 0x64, 0x6F, 0x6F, 0x21]
        crc = [0x36, 0x05, 0x9E, 0x14, 0x19, 0x7C]

        #transfer data
        cansend.send_msg(self.req_arb_id, header, is_multiframe=True)
        cansend.send_msg(self.rsp_arb_id, [0x76, 0x01])
        cansend.send_msg(self.req_arb_id, b1, is_multiframe=True)
        cansend.send_msg(self.rsp_arb_id, [0x76, 0x02])
        cansend.send_msg(self.req_arb_id, b2, is_multiframe=True)
        cansend.send_msg(self.rsp_arb_id, [0x76, 0x03])
        cansend.send_msg(self.req_arb_id, b3, is_multiframe=True)
        cansend.send_msg(self.rsp_arb_id, [0x76, 0x04])
        cansend.send_msg(self.req_arb_id, crc)
        cansend.send_msg(self.rsp_arb_id, [0x76, 0x05])

        #TODO:use elsewhere
        pay=bytes(b1[2:]+b2[2:]+b3[2:])
        print(pay)
        crc32 = binascii.crc32(pay) & 0xFFFFFFFF  # Ensure unsigned 32-bit result
        # Show as hex
        print("Expected CRC: 0x7191998A")
        print(f"Recieved CRC32: {crc32:#010x}")

        #request transfer exit
        req_exit = [0x37]
        cansend.send_msg(self.req_arb_id, req_exit)
        cansend.send_msg(self.rsp_arb_id, [0x7F, 0x37, 0x72])

    def handle_request(self, payload, cansend, verbose=False, multiframe=False):
        if (verbose): print(len(payload))
        payload_bytes = re.split(r'\s+', payload)
        if multiframe == True:
            dlc = len(payload_bytes)
            service_id = int(payload_bytes[0], 16)
        else:
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
        if isinstance(service, DiagnosticSessionControl):
            self.active_session = service.get_diagnostic_session(payload_bytes, trigger=True)
            if (verbose): print("Active session is:", self.active_session)
        rsp = service.construct_msg(payload_bytes, special_case=True)
        if (verbose): print(rsp)
        if self.active_session == 0x02 or isinstance(service, DiagnosticSessionControl):
            if rsp == [0x74, 0x10, 0x2E]:
                if (verbose): print("success yuh")
                cansend.send_msg(self.rsp_arb_id, rsp)
                self.req_download_complete = True
                config.ota_flash_status = 0x02
                cansend.broadcast_tcu_data()
            elif isinstance(service, TransferData):
                if self.req_download_complete == True:
                    if rsp == [0x76, service.sequence_number]:
                        print("yuhhhhh")
                        cansend.send_msg(self.rsp_arb_id, rsp)
                        self.valid_crc = service.get_update_payload(payload_bytes)
                    else:
                        cansend.send_msg(self.rsp_arb_id, rsp)
                else:
                    cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x24])
            elif isinstance(service, RequestTransferExit):
                if self.req_download_complete == True:
                    if self.valid_crc == True:
                        if rsp == [0x77]:
                            print("YUHHHHH")
                            cansend.send_msg(self.rsp_arb_id, rsp)
                            config.ota_flash_attempts += 1
                            config.ota_flash_status = 0x03
                            cansend.broadcast_tcu_data()
                            if config.client_sock:
                                config.client_sock.sendall("0x12".encode('utf-8'))
                        else:
                            cansend.send_msg(self.rsp_arb_id, rsp)
                    else:
                        cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x72])
                        config.ota_flash_attempts += 1
                        config.ota_flash_status = 0x01
                        cansend.broadcast_tcu_data()
                        if config.client_sock:
                            config.client_sock.sendall("0x12".encode('utf-8'))

                else:
                    cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x24])
            else:
                cansend.send_msg(self.rsp_arb_id, rsp)
        else:
            cansend.send_msg(self.rsp_arb_id, [0x7F, service_id, 0x7F])
'''
Filename: tcu.py
Author: CANQuest Team
Version: 1.0prod
Description: Custom Telematics Control Module (TCU) class used for CHV. Inherits from the ECU class.
'''

from .ecu import ECU
from services.uds_services import *
import server.config as config
'''
Filename: ivi.py
Author: CANQuest Team
Version: 1.0prod
Description: Custom In-Vehicle Infotainment (IVI) class used for CHV. Inherits from the ECU class.
'''

from .ecu import ECU
from services.uds_services import *
import server.config as config
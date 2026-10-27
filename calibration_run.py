# -*- coding: utf-8 -*-
"""
Created on Mon Nov  4 09:53:15 2024


In this module you call the SLM calibration class and save the 
images you take for a given range of SLM bits. This is then saved into
the directory (usually SLM_scan_files) as a .dat file. You also save
an additional info file, which contains the parameters of your .dat file, so you
can call it later (shape, dtype, etc.)




@author: anej
"""

from Calibration import SLMcalibration
import numpy as np
from pathlib import Path
import time
from paths import CALIBRATION_FOLDER





# exp_time = float(input('Running the calibration scan. Please select the exposure time in microseconds: '))
exp_time = 5.0e5
name_file = str(input('Name of your file: ')) + '.dat'
cal = SLMcalibration()
cal.init_camera(exposure_time =  exp_time)
cal.init_SLM() 

#Set the structure to some pattern of all the same values


rgbimg = SLMcalibration.convert_to_RGB(500*np.ones((1200,1920))).astype(dtype=np.int8)[::-1, ::-1, :]     #Moraš zrcalit!!!
#Update the SLM screen, but first do the covnersion to RGB space
cal.slm.updateArray(rgbimg)
time.sleep(1.2)
cal.get_region()  #To write the ROI coordinates.


# cal.Imin = 324
# cal.Imax = 995
# cal.Jmin = 71
# cal.Jmax = 1149

# (40.0, 11.2, 1119.2, 686.4)


# Define the file where the memory-mapped array will be stored
dire = Path(CALIBRATION_FOLDER) #On the external disk (set in paths.py)

dtype = 'float32'  # Choose appropriate data type, e.g., float32 or float64

# Define the bit array 
# bits = np.linspace(0, 1024, 100, dtype=int)
# bits  = np.linspace(200, 900, 200, dtype=int )

step = 2
bits = np.arange(0, 1023, step=step)
# bits = np.arange(0, 1023, step=20)
# bits = np.arange(200, 900, 1, dtype=int)
# bits = np.arange(0, 1024, 1, dtype=int)
# bits = np.linspace(420, 460, 40, dtype=int )

#Scan the whole SLM bit space
cal.SLM_scan(dire, name_file, bits, dtype=dtype, n_average = 4, sigma=1, plot = True)

#Release the camera
cal.close_camera()


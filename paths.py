# -*- coding: utf-8 -*-
"""
Data folders for the SLM scripts (calibration scans, wanted patterns and
optimized structures). They live on the external disk, so change DATA_ROOT
here if the disk gets a different drive letter or you move the data.
"""

import os

###### CHANGE THIS IF THE EXTERNAL DISK GETS A DIFFERENT DRIVE LETTER ######
#(or set the SLM_DATA_ROOT environment variable, e.g. on another machine or for a NAS: \\server\share\SLMwGUI_data)
DATA_ROOT = os.environ.get('SLM_DATA_ROOT', r'D:\SLMwGUI_data')

CALIBRATION_FOLDER = os.path.join(DATA_ROOT, 'SLM_scan_files')                 #Calibration scans (.dat + _info.npz)
PATTERNS_FOLDER = os.path.join(DATA_ROOT, 'SLM_patterns')                      #Wanted patterns (.npy)
OPTIMIZED_STRUCTURES_FOLDER = os.path.join(DATA_ROOT, 'SLM_optimized_structures')  #Optimized structures (.npz)


def find_calibration_dat(calib_info_loc, stored_location):
    """
    Location of the big calibration .dat file. The _info.npz stores the
    absolute path the scan was saved to, so if the files were moved (other
    disk, NAS) look for the .dat next to the _info.npz instead.
    """
    if os.path.isfile(stored_location):
        return stored_location

    dat_name = os.path.basename(str(calib_info_loc)).replace('_info.npz', '.dat')
    moved_location = os.path.join(os.path.dirname(str(calib_info_loc)), dat_name)
    if os.path.isfile(moved_location):
        return moved_location

    raise FileNotFoundError(f"Calibration data not found at {stored_location} or {moved_location}")


#Create the folders if the disk is plugged in and they don't exist yet
try:
    for folder in (CALIBRATION_FOLDER, PATTERNS_FOLDER, OPTIMIZED_STRUCTURES_FOLDER):
        os.makedirs(folder, exist_ok=True)
except OSError as e:
    print(f"WARNING: cannot access {DATA_ROOT} - is the external disk connected? ({e})")

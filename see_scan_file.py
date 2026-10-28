# -*- coding: utf-8 -*-
"""
Created on Wed Nov 13 07:42:55 2024



This is used to check the scanned files and their saved data.



@author: strco
"""


import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import os
from skimage.transform import resize       #To resize the images to your desired scale
from scipy.optimize import curve_fit 
from tqdm import tqdm
import numba as nb
from scipy.interpolate import RectBivariateSpline
from scipy.interpolate import RBFInterpolator, splrep,splev
import pickle
from paths import find_calibration_dat, CALIBRATION_FOLDER





    





############### RUN THE CODE FROM HERE ON DOWN ###################




##################### SET THE LOCATION OF YOUR SCAN FILE ###########################
#Get the parameter location in SLM scan files.
calib_info_loc = Path(CALIBRATION_FOLDER)/'9_6_2025_info.npz'
##################### SET THE LOCATION OF YOUR SCAN FILE ###########################



try:
    metadata = np.load(calib_info_loc, allow_pickle= True)
except:
    print('Could not data file! See if it exists at a given location')
    
# Load necessary location 
bits = metadata['bits']         #The given bit the SLM scan was done for
bar_shape = tuple(metadata['bar_shape'])   #The shape of the big SLM array 
bar_dtype = str(metadata['bar_dtype'])   #The dtype of values in the big SLM array
bar_location = find_calibration_dat(calib_info_loc, str(metadata['location'])) #The location of your big array (also if it was moved)


#Load the barshape 
N_bits, N_roi, M_roi, Nstokes = bar_shape


#Read the mmap array
calibmap = np.memmap(bar_location, dtype=bar_dtype, mode='r', shape=bar_shape)


s1ij = calibmap[...,0].copy()
s2ij = calibmap[... ,1].copy()
s3ij = calibmap[... ,2].copy()
    

#p parameter

pij = np.sqrt(s1ij**2 + s2ij**2)
psi = 0.5*np.arctan2(s2ij,s1ij)*180/np.pi


#Check which index is the same as the last one
psi_mean = np.mean(psi, axis=(1, 2))

f,a = plt.subplots(1)
a.plot(bits, psi_mean, '-o')

plt.show()



zero_crossings = np.where(np.diff(np.sign(psi_mean)))[0]

ind_first = zero_crossings[0]
ind_fifth = zero_crossings[4]

bit_first = bits[ind_first]
bit_fifth = bits[ind_fifth]

print(f'First crossing of zero at : {bit_first} bit' )
print(f'Fifth crossing of zero at : {bit_fifth} bit' )


# =============================================================================
# # Define the crossing value
# v = 0.0
# 
# # Compute differences from the target value
# diffs = s2mean - v
# 
# # Find where the sign of the difference changes (i.e., crossing)
# crossings = np.where(np.diff(np.sign(diffs)))[0]
# 
# =============================================================================



# np.savez(Path.cwd()/'psi_over_range'/'psi_mean_whole_range.npz', psi_mean = psi_mean, bits = bits)

# =============================================================================
# f,a = plt.subplots(1)
# a.plot(bits, psi_mean, '-o')
# 
# 
# 
# #Randomly choose 10 unique pixel coordinates
# num_pixels = 5
# x_coords = np.random.randint(0, pij.shape[2]-1, num_pixels)
# y_coords = np.random.randint(0, pij.shape[1]-1, num_pixels)
# 
# fig,ax = plt.subplots(1, 2)
# 
# # Set the chosen pixels to 1 (or another value to make them stand out)
# for i, j in zip(x_coords, y_coords):
#     ax[0].scatter(bits, psi[:,j,i])
#     ax[1].plot(bits, pij[:,j,i])
# 
# plt.show()
# =============================================================================



# fig,ax = plt.subplots(1,2)
# ax[0].imshow(pij[80,:,:], vmin = 0, vmax=1)
# ax[1].imshow(pij[30,:,:], vmin = 0, vmax=1)



# fig1,ax1 = plt.subplots(1)
# im1 = ax1.imshow(psi_wanted, cmap='plasma', vmin =-90, vmax  =90, animated=True)
# cbar1 = plt.colorbar(im1, ax= ax1)
# ax1.set_title('Kako zgleda')
# plt.show()

# fig,ax = plt.subplots(1)
# im1 = ax.imshow(optimal_bits, cmap='plasma', vmin =0, vmax  =1023, animated=True)
# cbar1 = plt.colorbar(im1, ax= ax)
# ax.set_title('Optimal bits')
# plt.show()



















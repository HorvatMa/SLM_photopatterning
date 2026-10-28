# -*- coding: utf-8 -*-
"""
Created on Thu May 29 12:23:09 2025

@author: PolarBear2017
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
from paths import find_calibration_dat




def transform_to_90_m90_range(angle_array):
    transformed = np.zeros_like(angle_array)
    
    
    #If you have values between 0 and -90 leave them be
    mask_neg = (angle_array < 0) & (angle_array >= -90)
    transformed[mask_neg] = angle_array[mask_neg]
    
    
    mask_q1 = (angle_array >= 0) & (angle_array <= 90)
    transformed[mask_q1] = angle_array[mask_q1]
    
    mask_q2 = (angle_array > 90) & (angle_array <= 180)
    transformed[mask_q2] = angle_array[mask_q2] - 180
    
    mask_q3 = (angle_array > 180) & (angle_array <= 270)
    transformed[mask_q3] = angle_array[mask_q3] - 180
    
    mask_q4 = (angle_array > 270) & (angle_array <= 360)
    transformed[mask_q4] = angle_array[mask_q4] - 360
    
    transformed = np.clip(transformed, a_min = -90, a_max=90)
    
    return transformed



@nb.jit(nopython=True)
def calculate_wanted_stokes(psi = 45):
    '''
    Calculate the wanted stokes vectors, pressuming the p=1 and I=1.. Here you dont have
    the chi dependency, because you already 'normalized' stokes vectors in the calibration fit.

    Parameters
    ----------
    psi : psi angle, describing the angle of polarization in degrees (float) . The default is 45.
    
    Returns
    -------
    Calculates normalized S1, S2.

    '''
        # Convert angles to radians
    psi_rad = np.deg2rad(psi)
    
    # Calculate normalized Stokes parameters
    s1_wanted = np.cos(2 * psi_rad)
    s2_wanted = np.sin(2 * psi_rad)

    return s1_wanted, s2_wanted
        

def get_best_psi(psiwanted, calib_info_loc, lamb = 1., bit_b = [80, 1010], phase_b = [90, 450], with_psi = False, progress_callback=None):
    '''

    Parameters
    ----------
    psiwanted : array of shape (1200, 1920) that contains wanted polarization in each pixel. The values
    need to be from 0 to 360. IN DEGREES!
    
    calib_info_locc: location (str)  of your whole calibration scan info file.
    
    lamb: float that tells you the weighting parameter in the minimization function,
    that is needed to make the bit map be smooth.
    
    
    with_psi: bool, if you set this to True it will calculate optimal psi
    with calculated psis, not with stokes vectors.
    
    progress_callback: function that gets called with the current iteration index to update progress in the GUI.
    
    
    Returns
    -------
    optimal_bits = array of shape (1200, 1920) that contains int from 0 to 1023, that correspond 
    to optimal bits that you need to send to SLM, to get a desired structure.

    '''

    
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
    
    print('loaded the map...')
    
    
    #This is your array of wanted polarization values (range 0 to 360)
    psismaller360 = resize(psiwanted,(N_roi, M_roi), preserve_range=True, order=0)
    
    #Now convert this array to range (-90,90) (what the camera saw)
    psismaller =  -transform_to_90_m90_range(psismaller360)
    
    
    
    ################# MAPPING BETWEEN BITS AND 0-2PI PHASE #######################
    #Get the lower and upper bound of your bits
    bit_lower  = bit_b[0]
    bit_upper = bit_b[1]
    
    #Make a masking array for bits between lower and upper values
    bit_mask= (bits >= bit_lower) & (bits <= bit_upper)
    
    #Get the indices of the value at lower and upper bound in the original array
    ind_first, ind_last  = np.where(bit_mask)[0][0], np.where(bit_mask)[0][-1]+1
    
    
    #Throw an error, if the values are not in the bounds
    if not np.any(bit_mask):
       raise ValueError(f"No elements within range [{bit_lower}, {bit_upper}]. The measured range of bits is [{bits[0]}, {bits[-1]}].")
       
     
    bits_short  =  bits[ind_first:ind_last]
    
    
    #Get the lower and upper bounds of your phase
    phase_lower = phase_b[0]
    phase_upper = phase_b[1]
    
    
    full_phase  = np.linspace(phase_lower, phase_upper, num=len(bits_short))%360
    ################################################################################
    
    

    
    optimal_bits = np.zeros((bar_shape[1], bar_shape[2]))
    
    
    
    s1ij_targ, s2ij_targ  = calculate_wanted_stokes(psi=psismaller)
        
    #Copy the calibmap in 10 by 10 chunks
    row_chunk = bar_shape[1]//10    #HARDCODED. YOU HAVE 10 BY 10 CHUNKS.
    col_chunk = bar_shape[2]//10
    
    print('optimizing...')
    
    n_chunk_processed = 0
    
    
    for i in range(0, bar_shape[1], row_chunk):
        for j in range(0, bar_shape[2], col_chunk):
            
            
            map_chunk = calibmap[ind_first:ind_last,i:i+row_chunk, j:j+col_chunk,:]
            s1_chunk = map_chunk[...,0].copy()
            s2_chunk = map_chunk[...,1].copy()
            s3_chunk = map_chunk[...,2].copy()
            
            
            chii = 0.5*np.arcsin(s3_chunk)
            cos_chi = np.cos(2 * chii)
            
            #This is I*p factor, which is equal to sqrt(S1**2 + S2*+2 + S3**2)
            Ip = np.sqrt(s1_chunk**2 + s2_chunk**2 + s3_chunk**2)
            
            
            s1_chunk /= cos_chi
            s2_chunk /= cos_chi
            
            
            s1_w_chunk = s1ij_targ[i:i+row_chunk, j:j+col_chunk]
            s2_w_chunk = s2ij_targ[i:i+row_chunk, j:j+col_chunk]
            
            if with_psi:
                psi = 0.5*np.arctan2(s2_chunk,s1_chunk)*180/np.pi
                costij = np.abs(psi-psismaller[i:i+row_chunk, j:j+col_chunk])
                costij =np.minimum(costij, 180-costij)

                argmin_indices = np.argsort(costij, axis=0)[0]
                
            else:
                costij = (s1_chunk - s1_w_chunk)**2 + (s2_chunk - s2_w_chunk)**2
                
                #Get your chunk of an array with values from 0 to 360
                psi360chunk = psismaller360[i:i+row_chunk, j:j+col_chunk]
                
                #Calculate the difference between your chunk array and the values of the phase (in degrees of course!)
                dif = (psi360chunk - full_phase[:, None, None])**2
                
                #Norm it so the values go from 0 to 1
                dif/= np.max(dif)
                
                
                costfull = np.sqrt(costij + lamb*dif)
                
                argmin_indices = np.argmin(costfull, axis=0)
                
    
            
            optimal_bits[i:i+row_chunk, j:j+col_chunk] = bits_short[argmin_indices]
            
            #Update at which chunk you are at
            n_chunk_processed += 1
            
            # Call the progress callback if it was passed
            if progress_callback:
                progress_callback(n_chunk_processed)  # This will call the update_progress method in the GUI

                
                
            
    optimal_bits_full = resize(optimal_bits,(1200, 1920),  preserve_range=True, order=0) 
     
     
     
    return optimal_bits_full



# =============================================================================
# 
# #create homogenous array of np.pi in the size of the slm
# Ny = 1200
# Nx = 1920
# 
# #Create splaybend circle
# 
# # Create an array with values ranging from 0 to 255
# gradient = np.linspace(0, 90, Nx, dtype = int)
# # Repeat the gradient for 1200 rows
# img_10bit = np.tile(gradient, (Ny, 1))
# 
# 
# optimal_bits_full  = get_best_psi(img_10bit, Path.cwd()/'SLM_scan_files'/'30_5_2025_2pi_info.npz' , lamb = 1., bit_b = [0, 840], phase_b = [50, 410], with_psi = False, progress_callback=None)
# 
# 
# 
# 
# 
# =============================================================================

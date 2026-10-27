# -*- coding: utf-8 -*-
"""
Polarization-camera (Sony IMX250MZR) image functions.

The raw mono image of the polarization camera is a 2x2 superpixel mosaic of
four polarizer orientations:

    [ 90  135]
    [ 45    0]

These functions split the raw image into the four channels and calculate the
Stokes parameters. They were taken from the spinview library (only the parts
used by this program), so the program doesn't depend on it anymore.
"""

import numpy as np

DEGREE =  180/np.pi
RADIAN =  1

UNITS = {"degree" : DEGREE, "radian" : RADIAN}


def validate_image(im):
    """Returns a validated image or raises an exception if invalid data."""
    im = np.asarray(im)
    #image must be 2D. Color data is not supported
    if im.ndim != 2:
        raise ValueError("Image is not 2D!")
    return im

def get_norm_factor(dtype, bit_depth = None):
    """Returns the scaling factor for image normalization"""
    if dtype == "uint8":
        return 1/255.
    elif dtype == "uint16":
        if bit_depth is not None:
            return 1./(2**bit_depth-1)
        return 1/65535.
    #assume it must have been converted and scaled already.
    elif dtype == "float":
        return 1.
    else:
        raise ValueError("Cannot determine norm factor from image dtype.")

def scale_image(im, bit_depth = None):
    """Returns a version of the image scaled to [0,1]"""
    norm = get_norm_factor(im.dtype, bit_depth)
    if norm != 1.:
        return im*norm
    else:
        return im


def i90(im):
    """Extracts pixels with vertical polarization from raw image"""
    im = validate_image(im)
    return im[::2,::2]

def i45(im):
    """Extracts pixels with +45 polarization from raw image"""
    im = validate_image(im)
    return im[1::2,::2]

def i0(im):
    """Extracts pixels with horizontal polarization from raw image"""
    im = validate_image(im)
    return im[1::2,1::2]

def i135(im):
    """Extracts pixels with 135 (-45) polarization from raw image"""
    im = validate_image(im)
    return im[::2,1::2]

def polar_image(raw, polar_axis = -1):
    """Converts 2D raw image to a 3D polar image. With polar_axis you can define
    the 4-length polarization coordinate axis.

    The polarization coordinates are 0 : i90, 1 : i45, 2 : i135 and 3 : i0.
    """
    height, width = raw.shape

    if polar_axis == 0:
        out = np.empty((4,height//2,width//2),dtype = raw.dtype)
        out[0] = i90(raw)
        out[1] = i45(raw)
        out[2] = i135(raw)
        out[3] = i0(raw)
    elif polar_axis in (-1,2):
        out = np.empty((height//2,width//2,4),dtype = raw.dtype)
        out[...,0] = i90(raw)
        out[...,1] = i45(raw)
        out[...,2] = i135(raw)
        out[...,3] = i0(raw)
    else:
        raise ValueError("polar axis must either be 0 (first) or -1 (last)")
    return out


def s0(im):
    """Stokes S0 parameter from the raw image"""
    #Scale first (uint8/uint16 -> float), this also prevents overflows
    im = scale_image(im)
    return i0(im) + i90(im)

def s1(im):
    """Stokes S1 parameter from the raw image"""
    im = scale_image(im)
    return (i0(im) - i90(im))

def s2(im):
    """Stokes S2 parameter from the raw image"""
    im = scale_image(im)
    return (i45(im)  - i135(im))

def s3(s0,s1,s2, p = 1.):
    """Stokes S3 parameter from S0, S1 and S2.
    Note that this assumes that input light is 100% polarized (p=1 in wikipedia formula) """
    return np.sqrt(np.clip(p**2 * s0**2 - (s1**2 + s2**2),0,None))

def stokes(im, p = 1., stokes_axis = -1):
    """Creates the stokes array (S0, S1, S2, S3) from the raw image.
    Note that this assumes that input light is 100% polarized (p=1 in wikipedia formula) """
    im = validate_image(im)
    height,width = im.shape
    im = scale_image(im)
    if stokes_axis in (-1,2):
        out = np.empty((height//2, width//2,4), dtype = "float")
        out[:,:,0] = s0(im)
        out[:,:,1] = s1(im)
        out[:,:,2] = s2(im)
        out[:,:,3] = s3(out[:,:,0],out[:,:,1],out[:,:,2], p = p)
    elif stokes_axis == 0:
        out = np.empty((4,height//2, width//2), dtype = "float")
        out[0] = s0(im)
        out[1] = s1(im)
        out[2] = s2(im)
        out[3] = s3(out[0],out[1],out[2], p = p)
    else:
        raise ValueError("stokes axis must either be 0 (first) or -1 (last)")

    return out

def psi(stokes, unit = "degree", stokes_axis = -1):
    """Returns polarization ellipse psi angle (angle of polarization) from the stokes vector of shape (...,4)."""
    norm = 0.5 * UNITS[unit]
    stokes = np.moveaxis(stokes, stokes_axis, 0)
    return np.arctan2(stokes[2], stokes[1])* norm

def chi(stokes,unit = "degree", stokes_axis = -1):
    """Returns polarization ellipse chi angle (ellipticity) from the stokes vector of shape (...,4)."""
    norm = 0.5 * UNITS[unit]
    stokes = np.moveaxis(stokes, stokes_axis, 0)
    return np.arctan2(stokes[3], np.sqrt(stokes[1]**2 + stokes[2]**2) ) * norm


# -*- coding: utf-8 -*-
"""
Created on Mon Dec  2 07:38:28 2024

The library to make patterns for SLM.


@author: strco
"""



import numpy as np
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from numba import njit


def transform_to_90_m90_range(angle_array):
    transformed = np.zeros_like(angle_array)
    
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
    

def add_text(text, input_arr, fill_value = 1.5, tbox_fill_value = np.pi, fontsize=150, lower_margin=20, box_margin = 15, font="arial"):
    """
    Add text to the bottom of an input array.

    Parameters:
    text (str): The text to be added to the array.
    input_arr (np.ndarray): The input array to which the text will be added, should be a 2D numpy array.
    fill_value (float): fill_value = text "colour" (basically the polarization angle value). Default is 1.5 for 0-pi.
                        Remember that under POM you see biggest contrast when text is + pi/2 from background.
    tbox_fill_value (float): fill_value = "colour" of the box. Default is 0. for 0-pi.
    fontsize (int, optional): The size of the font. Default is 100.
    lower_margin (int, optional): The margin between the bottom of the array and the text. Default is 20.
    box_margin (int, optional): The margin between the text and the background of the text (the box). Default is 15.
    font (str, optional): The name of the font to be used. Default is "arial".

    Returns:
    np.ndarray: A numpy array with the text added to the bottom.
    
    If needed, change the "text" parameter to also accept a list of strings,
    such as ["splay", "bend"] and place each of them to a designated anchor
    which can be default (width / len(texts) - text_i/2 ...) or from parameter.
    """
    
    # Transform input array to PIL image
    image = Image.fromarray(input_arr)
    
    #Draw area
    draw = ImageDraw.Draw(image)
        
        
    # Create font
    pil_font = ImageFont.truetype(font + ".ttf", size=fontsize, encoding="unic")
    
    # Set dimensions and anchor points
    width, height = int(len(input_arr[0])), int(len(input_arr))
    
    bbox = pil_font.getbbox(text)  # Returns (left, top, right, bottom)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]


    
    anchor_x, anchor_y = int(width/2) - int(text_width/2), height - text_height - lower_margin
    
    #Draw textbox
    bbox = draw.textbbox((anchor_x, anchor_y), text, font=pil_font)
    bbox = [bbox[i]-box_margin if i <= 1 else bbox[i]+box_margin for i in range(4)]
    # Draw a filled rectangle with this textbox
    draw.rectangle(bbox, fill=tbox_fill_value)
    
    #Draw text
    draw.text((anchor_x, anchor_y), text, font=pil_font, fill=fill_value)
    
    
    # Convert the canvas to a np array
    canvas_asarray = np.asarray(image)
    
    return canvas_asarray


def splay_line(input_arr, splay_angle = 20, width = 50, relative_position = 0.5, plot = True):
    '''
    Parameters
    ----------
    input_arr : (np.ndarray): The input array is a Ny x Nx array for SLM. Must be a numpy array
    splay_angle : (float) splay angle between 0 and 90. Must be positive! Tells you how much the director splays from the original position.
    width : (int) width of the splay line in pixels. The default is 50.
    relative_position : (float) relative position of the center y coordinate on the canvas, between 0 and 1. The default is 0.5 (in the middle)
    lie in the range [0,180] degrees. Otherwise it uses standard calibration from -90 to 90 degrees. Default is False.
    plot: Bool, if true it plots the dependency of the angles of the spline line
   
    
    Returns
    -------
    np.ndarray: A numpy array with the drawn splay line (values in radians)

    '''
    
    #Make a copy of the canvas
    canvas = np.copy(input_arr)
    Ny, Nx = canvas.shape
    

    if splay_angle < 0:
        splay_angle = np.abs(splay_angle)
        print('Kot je bil negativen, zato ga spreminjam v pozitivnega.')
    elif splay_angle == 0:
        print('Maksimalen kot odmika direktorja je 0...Povečaj, če hočeš imeti splay line.')
        
    elif splay_angle >= 90:
        print('WARNING! Your polarization angles are bigger than 90 degrees!. You want to keep it in range [0,90] degrees.')
        
        

    x = np.arange(int(width)) #generates part of the y axis for the splay line
    k = 2*np.pi/width #periodicity


    #Make a splay line
    y_pos = -splay_angle * np.sin(k*x) 
    
    mask_neg= (y_pos <= 0)
    y_pos[mask_neg] += 180
    
    # y_pos = splay_angle*np.sin(k*x)+splay_angle

    
    #graph corresponding sine wave
    if plot:
        fig,ax = plt.subplots(1)
        ax.plot(x, y_pos)
        ax.set_title('Sine Wave')
        ax.set_xlabel('x')
        ax.set_ylabel('y (angle in degrees)')
        plt.show()
        
    
    #Tile the values along the x direction
    y_2d = np.tile(y_pos, (Nx, 1)).T

    #insert splay line onto the canvas
    N_middle = int(relative_position*Ny)    #Calculate the index based on the relative position
    whalf = int(width/2)
    
    #To take care of the odd or even width
    if width % 2 == 0:
        canvas[N_middle-whalf:N_middle+whalf, :Nx] = y_2d
    else:
        canvas[N_middle-whalf:N_middle+1+whalf, :Nx] = y_2d
        
    return canvas

def bend_line(input_arr, bend_angle = 20,  width = 50, relative_position = 0.5, plot = True):
    '''
    Parameters
    ----------
    input_arr : (np.ndarray): The input array is a Ny x Nx array for SLM. Must be a numpy array
    splay_angle : (float) splay angle between 0 and 90. Must be positive! Tells you how much the director splays from the original position.
    width : (int) width of the splay line in pixels. The default is 50.
    relative_position : (float) relative position of the center y coordinate on the canvas, between 0 and 1. The default is 0.5 (in the middle)
    lie in the range [0,180] degrees. Otherwise it uses standard calibration from -90 to 90 degrees. Default is False.
    plot: Bool, if true it plots the dependency of the angles of the spline line

    Returns
    -------
    np.ndarray: A numpy array with the drawn splay line (values in radians)

    '''
    
    #Make a copy of the canvas
    canvas = np.copy(input_arr)
    Ny, Nx = canvas.shape
    

    if bend_angle < 0:
        bend_angle = np.abs(bend_angle)
        print('Kot je bil negativen, zato ga spreminjam v pozitivnega.')
    elif bend_angle == 0:
        print('Maksimalen kot odmika direktorja je 0...Povečaj, če hočeš imeti splay line.')
        
    elif bend_angle >= 90:
        print('WARNING! Your polarization angles are bigger than 90 degrees!. You want to keep it in range [0,90] degrees.')
        
        


    x = np.arange(int(width)) #generates part of the y axis for the splay line
    k = 2*np.pi/width #periodicity


    #Make a bend line
    y_pos = -bend_angle * np.sin(k*x)
    mask_neg= (y_pos <= 0)
    y_pos[mask_neg] += 180


    #graph corresponding sine wave
    if plot:
        fig,ax = plt.subplots(1)
        ax.plot(x, y_pos)
        ax.set_title('Sine Wave')
        ax.set_xlabel('x')
        ax.set_ylabel('y (angle in degrees)')
        plt.show()
        
    
    #Tile the values along the x direction
    y_2d = np.tile(y_pos, (Ny, 1))



    #insert splay line onto the canvas
    N_middle = int(relative_position*Nx)    #Calculate the index based on the relative position
    whalf = int(width/2)
    
    #To take care of the odd or even width
    if width % 2 == 0:
        canvas[:Ny, N_middle-whalf:N_middle+whalf] = y_2d
    else:
        canvas[:Ny, N_middle-whalf:N_middle+whalf+1]  = y_2d
        
    return canvas


def splay_line90(input_arr, splay_angle = 20, width = 50, relative_position = 0.5, plot = True):
    '''
    Parameters
    ----------
    input_arr : (np.ndarray): The input array is a Ny x Nx array for SLM. Must be a numpy array
    splay_angle : (float) splay angle between 0 and 90. Must be positive! Tells you how much the director splays from the original position.
    width : (int) width of the splay line in pixels. The default is 50.
    relative_position : (float) relative position of the center y coordinate on the canvas, between 0 and 1. The default is 0.5 (in the middle)
    lie in the range [0,180] degrees. Otherwise it uses standard calibration from -90 to 90 degrees. Default is False.
    plot: Bool, if true it plots the dependency of the angles of the spline line
   
    
    Returns
    -------
    np.ndarray: A numpy array with the drawn splay line (values in radians)

    '''
    
    #Make a copy of the canvas
    canvas = np.copy(input_arr)
    Ny, Nx = canvas.shape
    

    if splay_angle < 0:
        splay_angle = np.abs(splay_angle)
        print('Kot je bil negativen, zato ga spreminjam v pozitivnega.')
    elif splay_angle == 0:
        print('Maksimalen kot odmika direktorja je 0...Povečaj, če hočeš imeti splay line.')
        
    elif splay_angle >= 90:
        print('WARNING! Your polarization angles are bigger than 90 degrees!. You want to keep it in range [0,90] degrees.')
        
        

    x = np.arange(int(width)) #generates part of the y axis for the splay line
    k = 2*np.pi/width #periodicity

    #Make a splay line
    y_pos = 90 + splay_angle/2 * np.sin(k*x)

    
    #graph corresponding sine wave
    if plot:
        fig,ax = plt.subplots(1)
        ax.plot(x, y_pos)
        ax.set_title('Sine Wave')
        ax.set_xlabel('x')
        ax.set_ylabel('y (angle in degrees)')
        plt.show()
        
    
    #Tile the values along the x direction
    y_2d = np.tile(y_pos, (Nx, 1)).T

    #insert splay line onto the canvas
    N_middle = int(relative_position*Ny)    #Calculate the index based on the relative position
    whalf = int(width/2)
    
    #To take care of the odd or even width
    if width % 2 == 0:
        canvas[N_middle-whalf:N_middle+whalf, :Nx] = y_2d
    else:
        canvas[N_middle-whalf:N_middle+1+whalf, :Nx] = y_2d
        
    return canvas

    
def bend_line90(input_arr, bend_angle = 20,  width = 50, relative_position = 0.5, plot = True):
    '''
    Parameters
    ----------
    input_arr : (np.ndarray): The input array is a Ny x Nx array for SLM. Must be a numpy array
    splay_angle : (float) splay angle between 0 and 90. Must be positive! Tells you how much the director splays from the original position.
    width : (int) width of the splay line in pixels. The default is 50.
    relative_position : (float) relative position of the center y coordinate on the canvas, between 0 and 1. The default is 0.5 (in the middle)
    lie in the range [0,180] degrees. Otherwise it uses standard calibration from -90 to 90 degrees. Default is False.
    plot: Bool, if true it plots the dependency of the angles of the spline line

    Returns
    -------
    np.ndarray: A numpy array with the drawn splay line (values in radians)

    '''
    
    #Make a copy of the canvas
    canvas = np.copy(input_arr)
    Ny, Nx = canvas.shape
    

    if bend_angle < 0:
        bend_angle = np.abs(bend_angle)
        print('Kot je bil negativen, zato ga spreminjam v pozitivnega.')
    elif bend_angle == 0:
        print('Maksimalen kot odmika direktorja je 0...Povečaj, če hočeš imeti splay line.')
        
    elif bend_angle >= 90:
        print('WARNING! Your polarization angles are bigger than 90 degrees!. You want to keep it in range [0,90] degrees.')
        
        


    x = np.arange(int(width)) #generates part of the y axis for the splay line
    k = 2*np.pi/width #periodicity


    #Make a bend line
    y_pos = 90 + bend_angle/2 * np.sin(k*x)



    #graph corresponding sine wave
    if plot:
        fig,ax = plt.subplots(1)
        ax.plot(x, y_pos)
        ax.set_title('Sine Wave')
        ax.set_xlabel('x')
        ax.set_ylabel('y (angle in degrees)')
        plt.show()
        
    
    #Tile the values along the x direction
    y_2d = np.tile(y_pos, (Ny, 1))



    #insert splay line onto the canvas
    N_middle = int(relative_position*Nx)    #Calculate the index based on the relative position
    whalf = int(width/2)
    
    #To take care of the odd or even width
    if width % 2 == 0:
        canvas[:Ny, N_middle-whalf:N_middle+whalf] = y_2d
    else:
        canvas[:Ny, N_middle-whalf:N_middle+whalf+1]  = y_2d
        
    return canvas



    
def bend_line90_hom(input_arr, bend_angle = 20,  width = 50, hom_width = 50, relative_position = 0.5, plot = True):
    '''
    Parameters
    ----------
    input_arr : (np.ndarray): The input array is a Ny x Nx array for SLM. Must be a numpy array
    splay_angle : (float) splay angle between 0 and 90. Must be positive! Tells you how much the director splays from the original position.
    width : (int) width of the splay line in pixels. The default is 50.
    hom_width: (int) width of the homogenous middle region in pixels. The defaults is 50. 
    relative_position : (float) relative position of the center y coordinate on the canvas, between 0 and 1. The default is 0.5 (in the middle)
    lie in the range [0,180] degrees. Otherwise it uses standard calibration from -90 to 90 degrees. Default is False.
    plot: Bool, if true it plots the dependency of the angles of the spline line

    Returns
    -------
    np.ndarray: A numpy array with the drawn splay line (values in radians)

    '''
    
    #Make a copy of the canvas
    canvas = np.copy(input_arr)
    Ny, Nx = canvas.shape
    

    if bend_angle < 0:
        bend_angle = np.abs(bend_angle)
        print('Kot je bil negativen, zato ga spreminjam v pozitivnega.')
    elif bend_angle == 0:
        print('Maksimalen kot odmika direktorja je 0...Povečaj, če hočeš imeti splay line.')
        
    elif bend_angle >= 90:
        print('WARNING! Your polarization angles are bigger than 90 degrees!. You want to keep it in range [0,90] degrees.')
        
        


    x = np.arange(int(width)) #generates part of the y axis for the splay line
    k = 2*np.pi/width #periodicity


    #Make a bend line
    y_pos = 90 + bend_angle * np.sin(k*x)
    
    positives  = y_pos[y_pos > 90]
    negatives  =  y_pos[y_pos < 90]
    
    middle_part  = np.arange(int(hom_width))
    homog = np.full_like(middle_part, 90)
    
    
    
    y_pos = np.concatenate((positives, homog, negatives))
    new_xdim = np.arange(len(y_pos))
    

    #graph corresponding sine wave
    if plot:
        fig,ax = plt.subplots(1)
        ax.plot(new_xdim, y_pos)
        # ax.plot(x_positive, positives)
        # ax.plot(x_negative, negatives)
        ax.set_title('Sine Wave')
        ax.set_xlabel('x')
        ax.set_ylabel('y (angle in degrees)')
        plt.show()
        
    
    #Tile the values along the x direction
    y_2d = np.tile(y_pos, (Ny, 1))



    #insert splay line onto the canvas
    N_middle = int(relative_position*Nx)    #Calculate the index based on the relative position
    
    width_whole = len(y_pos)
    whalf = int(width_whole/2)
    
    
    
    #To take care of the odd or even width
    if width_whole % 2 == 0:
        canvas[:Ny, N_middle-whalf:N_middle+whalf] = y_2d
        print('ha')
    else:
        canvas[:Ny, N_middle-whalf:N_middle+whalf+1]  = y_2d

    return canvas





@njit  
def bend(input_arr, center, radius = 50):
    """
    Create a circle, with the angular part varying from 0 to 2pi (for a bend deformation).
    Parameters:
    input_arr (np.ndarray): The input array is a array, on which you will draw the circle. should be a 2D numpy array.
    center (2-element list or tuple): x and y coordinates of the circle center
    radius (int): radius of the circle in pixels. Default is 50 pixels.
    
    Returns:
    np.ndarray: A numpy array with the drawn image in angles from 0 to 360
    
    """
    cx, cy = center
    #Make a copy of the input_arr
    canvas = np.copy(input_arr)
    Nx, Ny = canvas.shape
    
    for x in range(Nx):
        for y in range(Ny):
            dx, dy = x - cx, y - cy
            distance = np.sqrt(dx**2 + dy**2)
            if distance <= radius:
                angle = np.arctan2(dy, dx)
                # If negative angle add pi, so you have [0,pi]
                if angle < 0:
                    angle += 2*np.pi
                        
                #Divide values by two so you get an interval 
                canvas[x, y] = angle

    return canvas

@njit
def splay(input_arr, center, radius=50):
    """
    Create a circle, with the angular part varying from 0 to 2pi (splay deformation).
    Parameters:
    input_arr (np.ndarray): The input array is a array, on which you will draw the circle. should be a 2D numpy array.
    center (2-element list or tuple): x and y coordinates of the circle center
    radius (int): radius of the circle in pixels. Default is 50 pixels.

    
    Returns:
    np.ndarray: A numpy array with the drawn image in angles from 0 to 360
    
    """
    cx, cy = center
    
    #Make a copy of the input_arr
    canvas = np.copy(input_arr)
    Nx, Ny = canvas.shape
    
    for x in range(Nx):
        for y in range(Ny):
            dx, dy = x - cx, y - cy
            distance = np.sqrt(dx**2 + dy**2)
            
            if distance <= radius:
                angle = np.arctan2(dy, dx)
                tangent = angle + np.pi/2
                tangent = (tangent + np.pi) % (2 * np.pi)
                canvas[x, y] = tangent
                
    return canvas


@njit
def sin2d(input_arr, pol_bounds = (0,90), x_period = 500, y_period = 40, plot=True):
    """
    Creates a 2D pattern .
    
    Parameters:
    - input_arr (np.ndarray): The input array is a array, on which you will draw the plane wave. should be a 2D numpy array.
    - pol_bounds (2-element tuple or list of floats): (lower_bound, upper_bound) tells you the min and max value of the sin wave in degrees. The sin wave
    will then oscillate between those two bounds.
    - x_period (int): period of the sin wave in the x direction (in pixels)
    - y_period (int): period of the shifted array in the y direction (in pixels)
    - plot(bool): if you want to see the plots of the structure
    
    Returns:
    np.ndarray: A numpy array with the drawn image of the 2d pattern
    
    """
    
    #Check if the values in bounds are reversed and switch thrm
    if pol_bounds[0] > pol_bounds[1]:
        # Swap the values
        pol_bounds = (pol_bounds[1], pol_bounds[0])
        # Print the warning message
        print("Warning: Values of the bounds were reversed due to lower bound being bigger than the upper bound.")
    
    
    #Make a copy of the input_arr
    canvas = np.copy(input_arr)
    Ny, Nx = canvas.shape

    k_x = 2*np.pi/int(x_period)
    k_y = 2*np.pi/int(y_period)
    x = np.arange(Nx)
    y = np.arange(Ny)
    
    X, Y = np.meshgrid(x, y)

    # Compute the 2D sine pattern
    sin2d = np.sin(k_x*X)* np.sin(k_y*Y)
    
    upper_b, lower_b = pol_bounds
    
    #scaled 2d sin pattern
    sin2d_s = sin2d * (upper_b - lower_b) / 2 + (upper_b + lower_b) / 2
    
    
    #fill the canvas and convert the degrees to radians
    canvas[:] = sin2d_s*(np.pi/180)
    
    
    if plot:
        fig3,ax3 = plt.subplots(1)
        im3 = ax3.imshow(sin2d_s, aspect='auto', cmap='viridis')
        ax3.set_title(r'2D sin wave')
        ax3.set_xlabel('x')
        ax3.set_ylabel('y')
        fig3.colorbar(im3, label='Amplitude in degrees')
        plt.show()


    
    return canvas


def splaybend(input_arr, center, radius=50, width=20, splay_angle = 30): #radius and width of the splay in px, amplitude in degrees
    
    """
    Create a circle with a bend deformation.
    Parameters:
    input_arr (np.ndarray): The input array is a array, on which you will draw the circle. should be a 2D numpy array.
    center (2-element list or tuple): y and x position of the circle
    radius (int): radius of the circle in pixels. Default is 50 pixels.
    width (int): width of the splay line in pixels. Default is 20 pixels.
    splay_angle (int): max splay angle in degrees. Default is 30 degrees.

    
    Returns:
    np.ndarray: A numpy array with the drawn image of angles in degrees
    
    """

    cx, cy = center
    
    
    #Make a copy of the input_arr
    canvas = np.copy(input_arr)
    
    for x in range(canvas.shape[0]):
        for y in range(canvas.shape[1]):
            dx, dy = x - cx, y - cy
            distance = np.sqrt(dx**2 + dy**2)
            
            if distance <= radius:
                angle = np.arctan2(dy, dx)
                
                if distance >= (radius//2 - width//2) and distance <= (radius//2 + width//2):
                   
                    if angle < 0:
                      angle += 2*np.pi
                      
                    #your splay line
                    k = 4*np.pi/width
                    a = (splay_angle*np.pi/180)* np.sin(k*(distance - radius//2 + width//2)) + angle


                    if a < 0:
                        a += 2*np.pi

                    canvas[x,y] = a
                    
                else:
                    if angle < 0:
                      angle += 2*np.pi
                    canvas[x, y] = angle 
    

    canvas  %= 2*np.pi

    return canvas

def bendsplay(input_arr, center, radius=50, width=20, bend_angle = 30): #radius and width of the splay in px, amplitude in degrees
    
    """
    Create a circle with a bend deformation.
    Parameters:
    input_arr (np.ndarray): The input array is a array, on which you will draw the circle. should be a 2D numpy array.
    center (2-element list or tuple): y and x position of the circle
    radius (int): radius of the circle in pixels. Default is 50 pixels.
    width (int): width of the splay line in pixels. Default is 20 pixels.
    bend_angle (int): max bend angle in degrees. Default is 30 degrees.

    
    Returns:
    np.ndarray: A numpy array with the drawn image of angles in degrees
    
    """

    cx, cy = center
    
    
    #Make a copy of the input_arr
    canvas = np.copy(input_arr)
    
    for x in range(canvas.shape[0]):
        for y in range(canvas.shape[1]):
            dx, dy = x - cx, y - cy
            distance = np.sqrt(dx**2 + dy**2)
            
            if distance <= radius:
                angle = np.arctan2(dy, dx)
                
                if distance >= (radius//2 - width//2) and distance <= (radius//2 + width//2):
                   
                    if angle < 0:
                      angle += 2*np.pi
                      
                    #your splay line
                    k = 4*np.pi/width
                    a = (bend_angle*np.pi/180)* np.sin(k*(distance - radius//2 + width//2)) + angle


                    if a < 0:
                        a += 2*np.pi

                    canvas[x,y] = a + np.pi/2
                    
                else:
                    if angle < 0:
                      angle += 2*np.pi
                    canvas[x, y] = angle + np.pi/2 
    

    canvas  %= 2*np.pi

    return canvas


from paths import PATTERNS_FOLDER
path = Path(PATTERNS_FOLDER) #Define the path of your data (on the external disk, set in paths.py)




#create homogenous array of np.pi in the size of the slm
Ny = 1200
Nx = 1920

#Create splaybend circle

angle = 0

empty_canvas = angle*np.ones((Ny,Nx))
cx = int(Nx/3)
cy = int(Ny/3)


psi_wanted  = empty_canvas 

psi_wanted = add_text(f' {angle}deg', input_arr=psi_wanted, fill_value=0, tbox_fill_value = 45, fontsize=80, lower_margin=50, font="arial")

# =============================================================================
# psi_wanted  = bendsplay(empty_canvas, (cy,cx), radius=300, width=150, bend_angle = 40)
#    
# =============================================================================
    
#Create splay lines (rotated by 90..so actually bend lines)
angle = 45
empty_canvas = 90*np.ones((Ny,Nx))
b1 = bend_line90_hom(empty_canvas, bend_angle = angle , width = 40,  hom_width = 50, relative_position = 0.15, plot = True)
b2 = bend_line90_hom(b1, bend_angle = angle , width = 30,  hom_width = 50,  relative_position = 0.3, plot = False)
b3 = bend_line90_hom(b2, bend_angle = angle , width = 20,  hom_width = 50, relative_position = 0.5, plot = False)
b4 = bend_line90_hom(b3, bend_angle = angle , width = 10,  hom_width = 50, relative_position = 0.7, plot = False)
final = add_text(f'angle {angle}deg, lines 80,100,150,200 px', input_arr=b4, fill_value=90, tbox_fill_value = 45, fontsize=80, lower_margin=50, font="arial")
psi_wanted = final



#Create bend and splay circles. Both in radians so you need to do a conversion (180 to pi)
# =============================================================================
# empty_canvas = (np.pi/2)*np.ones((Ny,Nx))
# b1 = bend(empty_canvas, (int(0.3*Ny),int(0.25*Nx)), radius = 250)
# b2 = bend(b1, (int(0.75*Ny),int(0.25*Nx)), radius = 150)
# s1 = splay(b2, (int(0.3*Ny),int(0.7*Nx)), radius = 250)
# s2 = splay(s1, (int(0.75*Ny),int(0.7*Nx)), radius = 150)
# 
# final = add_text(f'bend and splay', input_arr=s2, fill_value=np.pi/2, tbox_fill_value = np.pi/4, fontsize=80, lower_margin=50, font="arial")
# psi_wanted = final*180/np.pi
# 
# =============================================================================


#Get the transformed version into what the polarization camera sees:
    
trans_psi_wanted = transform_to_90_m90_range(psi_wanted)



fig,(ax,ax1) = plt.subplots(1, 2, figsize=(10,8))
im = ax.imshow(psi_wanted, cmap='viridis')
ax.axis('equal')
ax.set_xlabel('x')
ax.set_ylabel('y')
fig.colorbar(im, ax=ax,  label='Amplitude in degrees')

im1 = ax1.imshow(trans_psi_wanted, cmap='viridis')
fig.colorbar(im1, ax=ax1,  label='Amplitude in degrees')


plt.show()





# name_pattern = f'polarization_{angle}_wtext'
# np.save(path/name_pattern, psi_wanted) #saving array as csv, amplitude in radians
 


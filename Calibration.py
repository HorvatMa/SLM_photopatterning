# -*- coding: utf-8 -*-
"""
Created on Mon Nov 11 16:08:40 2024

@author: strco
"""




try:
    import PySpin  #FLIR Spinnaker SDK python wrapper (installed separately, see README)
except ImportError:
    PySpin = None  #Only needed for the camera (calibration scan), the SLM works without it
import polarimetry as stks        #From this module you can calculate stokes parameters
from polarimetry import polar_image
import numpy as np
import time
import atexit
import matplotlib.pyplot as plt
import slmpy #to je ta tvoja knjiznica ki fura slmpy
import shutil       #To check the memory
import os
from tqdm import tqdm
from RectangleFinder_v2 import ImageSelectorApp
import tkinter as tk
from skimage.filters import gaussian

            
            

class SLMcalibration:
    
    NORM = 2**16 -1 #max uint16 #norm za kamero.
    
    def __init__(self):
        #Initialize some variables
        self.cam_init_bool = False # Boolean to see if camera is initialized
        self.SLM_init_bool = False # Boolean to see if SLM is initialized

    @staticmethod
    def convert_to_RGB(input_array):
        
        '''
        Converts a 2D array (Nx by Ny) with values ranging from 0 to 1023 to a
        3D array (Nx by Ny by 3) which you can input into slmpy 'slm.updateArray' module to display on SLM
        as a secondary screen.
        
        Parameters:
            - input_array: 2D array (dimY x dimX) of values ranging from 0 to 1023 (indices).
        Returns:
            - rgb_array: 3D array (dimY x dimX x 3), where last index corresponds to three colors - red (0th index), green(1st index)
            and blue (2nd index). Example: getting only green channel of the image would be achieved like this: rgb_array[:,:,1]
            
            CAVEAT: this stays in int32 format. For usage in slmpy module, you must convert it to dtype=np.int8 like this:
                rgb_array = rgb_array.astype(dtype=np.int8)
        '''
        
        #Clip the array if you have some values that are not int or if they are out of range.
        input_array = np.clip(input_array, 0, 1023).astype(int)
        
        
        size = 1024
        # map red values 
        red = (np.arange(size, dtype=int) // 128) * 32
        green = ((np.arange(size, dtype=int)%128)//16)*32
        blue = (np.arange(size, dtype=int) % 16) * (256 // 16)
        
        rgbspace = np.column_stack((red, green, blue))
        
        
        # Map input values to RGB values using the rgb_map
        rgb_array = rgbspace[input_array] #.astype(dtype=np.int8)


        return rgb_array

    def init_camera(self, exposure_time  = 8):
        '''
        Initializes the first FLIR camera found with PySpin and sets it up for the scan.
        Parameters
        ----------
        exposure_time : Exposure time for the camera in microseconds. Default is 8 (min is 7).

        Returns
        -------
        None.

        '''
        if PySpin is None:
            raise ImportError('PySpin is not installed. Install the Spinnaker SDK and its python wheel (see README).')

        #Initializizes the camera. PySpin needs these references to be released in the right order, see close_camera
        self.system = PySpin.System.GetInstance()
        self.cam_list = self.system.GetCameras()

        if self.cam_list.GetSize() == 0:
            self.cam_list.Clear()
            self.system.ReleaseInstance()
            raise RuntimeError('No FLIR camera found!')

        self.cam = self.cam_list.GetByIndex(0)
        self.cam.Init()

        #Release the camera properly also if the program ends without calling close_camera
        atexit.register(self.close_camera)

        #Camera settings (the order matters: the auto modes have to be off before you set the values)
        self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_SingleFrame)      #I dont know why continuous doesnt work
        self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
        self.cam.ExposureTime.SetValue(min(max(exposure_time , 7.0), self.cam.ExposureTime.GetMax()))  #The exposure time must be at least 7.0
        if PySpin.IsWritable(self.cam.GammaEnable):
            self.cam.GammaEnable.SetValue(False)
        self.cam.GainAuto.SetValue(PySpin.GainAuto_Off)
        self.cam.Gain.SetValue(0.)
        self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono16)
        self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit12)

        print(f'Exposure time is {self.exposure_time}')

        self.cam_init_bool = True

    @property
    def exposure_time(self):
        '''Current exposure time of the camera in microseconds.'''
        return self.cam.ExposureTime.GetValue()

    def get_image(self):

        '''
        Captures an image with a camera and transforms it into a numpy array.
        '''

        #Creates a mono image array
        self.cam.BeginAcquisition()
        im = self.cam.GetNextImage(1000) #Prej blo 100
        NDarray = im.GetNDArray().copy()  #Copy, because the image buffer is freed with Release
        im.Release()
        self.cam.EndAcquisition()

        return NDarray

    def close_camera(self):
        '''
        Releases the camera and the PySpin system. Safe to call more than once.
        '''
        if not self.cam_init_bool:
            return

        try:
            if self.cam.IsStreaming():
                self.cam.EndAcquisition()
            self.cam.DeInit()
        finally:
            #All references to the camera must be gone before the system is released
            del self.cam
            self.cam_list.Clear()
            self.system.ReleaseInstance()
            self.cam_init_bool = False
        
    def init_SLM(self):
        '''
        Initializes the SLM class from slmpy library.

        Returns
        -------
        None.

        '''
        #Initialize SLM by opening the image on the second screen
        
        self.slm = slmpy.SLMdisplay(isImageLock = True)
        self.resX, self.resY = self.slm.getSize()
        
        self.SLM_init_bool = True

    def live_canvas(self):
        '''
        Initializes the canvas to draw different parameters.

        Returns
        -------
        self.fig - figure
        self.axs - list of axs
        '''
        # Create a figure with three subplots
        self.fig, self.axs = plt.subplots(1, 3, figsize=(15, 5))
        plt.ion()  # Turn on interactive mode

        # Create initial random images
        self.image1 = np.random.rand(2048,  2448)
        self.image2 = np.random.rand(2048,  2448)
        self.image3 = np.random.rand(2048,  2448)

        # Display the initial images and their colorbars
        self.im1 = self.axs[0].imshow(self.image1, cmap='plasma', vmin = -90, vmax  =90, animated=True)
        cbar1 = plt.colorbar(self.im1, ax= self.axs[0])
        self.axs[0].set_title('Polarization of light (in degrees)')
        
        self.im2 =  self.axs[1].imshow(self.image2, cmap='plasma', vmin = -90, vmax = 90, animated=True)
        cbar2 = plt.colorbar(self.im2, ax= self.axs[1])
        self.axs[1].set_title('Chi (how elliptic it is) ')
        
        self.im3 =  self.axs[2].imshow(self.image3, cmap='inferno', vmin=0, vmax=1, animated=True)
        cbar3 = plt.colorbar(self.im3, ax=self.axs[2])
        self.axs[2].set_title('Intensity')

        return self.fig, self.axs
         
    def get_region(self, which = 'polarization'):
        
        '''
        Get your region of interest and write the indices of your ROI (imin, imax, jmin, jmax) in an instance variable.
        Cropping your original picture would then be : image[Imin:Imax, Jmin:Jmax]
        
        which: string that tells whether you are looking at intensity or polarization values of the senzor. Default is
        'polarization', because you can more accurately determine the location of SLM activate area.
       
        '''
        
        #First take an image
        mono_img = self.get_image()
        intensity = polar_image(mono_img)/SLMcalibration.NORM
        max_values = intensity.max(axis = -1)
        mvalue = np.max(max_values)
        intensity_bit = (255*max_values).astype(np.uint8) 
        

        #Get the stokes vector from which you get values of s0, s1, s2 and s3
        s = stks.stokes(mono_img)
        pol = stks.psi(s)   #Angle of polarization
        polarization_bit  = 0 + ((pol - (-90)) * (255 - 0) / (90 - (-90))).astype(np.uint8) 


        ##### SHOW YOUR INTENSITY VALUE ON A GRAPH ############
        fig_i, ax_i  = plt.subplots(1,1)
        im1 = ax_i.imshow(max_values, cmap='plasma', vmin = 0, vmax  =1)
        cbar1 = plt.colorbar(im1,  ax= ax_i)
        ax_i.set_title(f'Max intensity across all channels. \n Max intensity: {mvalue:.3e}. Exposure: {self.exposure_time:.2f} microseconds.')
        ########################################################
        

        #Izberi si prvi frame in oznaci pravokotnike, ki jih zelis gledati.
        root = tk.Tk()
        
        #If you are looking at intensity or polarization values.
        if which == 'intensity':
            app = ImageSelectorApp(root, intensity_bit)
        else: 
            app = ImageSelectorApp(root, polarization_bit)
            
            
        root.mainloop()
        
        plt.close(fig_i)    #Close the figure.
        
        
        rect_di = {}
        
        #Rectangle names
        rects = [r for r in app.rectangles.keys()]
        
        
        # Prvo dobi velikost prvega oznacenega obmocja, ta ti bo določil število pikslov
        x1, y1 = app.rectangles[rects[0]]['top left']
        x2, y2 = app.rectangles[rects[0]]['bottom right']
        
        x1, y1, x2,y2 = int(x1), int(y1), int(x2), int(y2)
        
            
        self.Imin = y1
        self.Imax = y2
        self.Jmin = x1
        self.Jmax = x2
        

    @staticmethod
    def create_big_array(directory, filename, shape, dtype='float64'):
        '''
        Creates a big array (we are talking Gb!), so you can use it by chunks later on.
        
        PARAMETERS:
        directory: path to your directory (str)
        filename: name of your dat file (str). You need to name it something like 'example.dat'. If there is no .dat, it will be added,
        shape: shape of an array to create (tuple). Usually (1920,1200,1023) for SLM.
        dtype: What kind of format for values (str). Default: 'float64'
        
        RETURNS: big_array - your memory map
        '''
        
        
        # Check if the string ends with '.dat' (case-insensitive)
        if not filename.lower().endswith('.dat'):
            # If not, add the '.dat' extension
            filename += '.dat'
        
        

        # Calculate the size of the potential array in bytes
        element_size = np.dtype(dtype).itemsize  # Size of one element in bytes
        total_array_size = np.prod(shape, dtype=np.int64) * element_size  
        
        
        
        # Check available disk space in bytes
        total, used, free = shutil.disk_usage(os.path.dirname(directory))
        
        
        # Convert sizes to GB for easier reading
        free_gb = free / (1024 ** 3)
        total_array_size_gb = total_array_size / (1024 ** 3)
        
        # Calculate percentage of space used by the array relative to available space
        percentage_used = (total_array_size / free) * 100
        
        # Print storage info with color coding
        print(f"Free storage: {free_gb:.2f} GB")
        
        if total_array_size_gb < 1e-3:
            print(f"Required storage for the array: {total_array_size / (1024 ** 2):.2f} MB")
        else:
            print(f"Required storage for the array: {total_array_size_gb:.2f} GB")
        
        # Color the output based on storage usage
        if total_array_size < free:
            # Green for safe storage usage (less than 50% of available space)
            print(f"The array will take up" + f' {percentage_used:.2f}% ' + "of available space.")
        else:
            # Red for unsafe usage (more than available space)
            print(f"Not enough disk space! The array requires {percentage_used:.2f}% of available space.")
        
        print(f'The array will be saved at {directory/filename}')
        
        # Prompt the user for input
        user_input = input("Press Enter to create the array or 'q' to quit: ").strip().lower()
        
        if user_input == '':
            # Create the array if user pressed Enter
            print("Creating and saving the array...")
            
            # Create a memory-mapped array (saved on disk) if space is sufficient
            if total_array_size < free:
                bar = np.memmap(directory/filename, dtype=dtype, mode='w+', shape=shape)
                print("Memory-mapped array created and saved to disk.")
                return bar
            else:
                print("Failed to create the array due to insufficient disk space.")
                return None
                
        elif user_input == 'q':
            print("Operation cancelled. Array not created.")
            return None
        else:
            print("Invalid input. Please press Enter to create the array or 'q' to quit.")
            return None

    def SLM_scan(self, directory, filename, bits, dtype='float64', sigma = 0., n_average = 1, plot = True):
        
        
        '''
        
        Change the value of the bit on SLM and take a picture with a polarizing camera in the chosen 
        ROI. Then calculate normalized stokes vectors S1 and S2 (S1/S0 and S2/S0) for different bit values of the 
        SLM.
        

        directory: string to your directory, where the big calibrationn array is stored
        filename: string of your calibration file, which will be saved in the directory
        bits: np.array of your SLM bits (usually from 0 to 1024 in increments of 10)
        dtype: 'float64' or 'float32': the accuracy of your data. default float64.
        sigma: float, the sigma of the gaussian kernel that is applied over the intensity in all i90, i45,i0 and i135 channels. If 0, then no kernel is applied.
        n_average: int, tells you how many pictures you take at each bit to average them out.
        plot: bool, tells you if you want to plot while scanning. default True. 
        
        
        returns:/
        '''

        n_average = max(int(n_average), 1)
        print('Stevilo frameov pri vsakem bitu bo {n_average}.')
                
                
        # Calculate dimension of the ROI region
        N = int (self.Imax - self.Imin)
        M = int (self.Jmax - self.Jmin)
        #Get the length of the bits array
        N_bits = len(bits)
        
        
        #Shape of the big array is (N of bits, points in Y direction, points in X direction and 3 (for three stokes vectors))
        shapeb = (N_bits, N, M, 3)
            
        bar_location = directory/filename

            
        #Create this big array so you can store the variables
        bar = self.create_big_array(directory, filename, shapeb, dtype=dtype)
    
        # Create the metadata file (with the info you need to call the data array)
        mdata_name = filename.replace(".dat", "") + '_info.npz'
        mdata_loc = directory/mdata_name
        
        np.savez(mdata_loc, bits = bits, bar_shape = shapeb, bar_dtype = dtype, location=str(bar_location))
        print('Metadata saved.')
        
        
        
        if bar is None:
            print('Scan was not initiated because the placeholder array was not created.')
            return 0
        
        if not self.cam_init_bool:
            print('\n Initialize the camera! Closing the scan... \n')
            return 0
        
        if not self.SLM_init_bool:
            print('\n Initialize the SLM! Closing the scan...\n ')
            return 0
        
        
        
        if plot:
            fig,axs = self.live_canvas()


        # Start the loop over different values of SLM bits and get the stokes vectors
        
        for ibit in tqdm(range(len(bits))):
        
            slmimage = bits[ibit]*np.ones([self.resY,self.resX])
        
            #Update the SLM screen, but first do the covnersion to RGB space
            self.slm.updateArray(SLMcalibration.convert_to_RGB(slmimage).astype(dtype=np.int8))
            
            
            time.sleep(1.1)   #Sleep for at least 1 second! (because of the SLM response time)
        
        
        
            #Make a bigger array, so you will then average the channels.
            more_frames = np.empty((n_average, N, M, 4))
            
            for n_frame in range(n_average):
                
                #Take an image with the camera
                mono_img = self.get_image()
                intensity = polar_image(mono_img)/SLMcalibration.NORM
            
                #Take reduced intensity 
                int_smaller_ind = intensity[self.Imin:self.Imax, self.Jmin:self.Jmax, :]
                
                more_frames[n_frame, ...] = int_smaller_ind
            
            #Your average intensity is now just the mean over more frames (so you get rid of the noise.)
            int_smaller = np.mean(more_frames, axis=0)
            
            #Apply a gaussian filter over the whole thing if sigma is not zero
            if sigma != 0:
                #apply a gaussian filter
                int_smaller = gaussian(int_smaller, sigma=sigma, preserve_range=True,channel_axis=-1)


            
            max_values = int_smaller.max(axis = -1)  #Calculate the maximum intensity in all channels
            mvalue = np.max(max_values)
            
            
            i90 = int_smaller[..., 0] 
            i45  = int_smaller[..., 1] 
            i135  = int_smaller[..., 2] 
            i0  = int_smaller[..., 3] 


            s0_ROI = i0 + i90
            s1_ROI = i90-i0 #Kle sta intenziteti zamenjani zato da mas isto kot na kameri vidis
            s2_ROI = i135-i45
            s3_ROI = np.sqrt(np.clip(s0_ROI**2 - (s1_ROI**2 + s2_ROI**2),0,None))
            
            pol_in_ROI = 0.5*np.arctan2(s2_ROI,  s1_ROI)*180/np.pi # Polarization angle in degrees
            depol_in_ROI = 0.5*np.arctan2(s3_ROI, np.sqrt(s1_ROI**2 + s2_ROI**2) ) *180/np.pi
            
            
            #Fill the stokes arrays for a given frame
            bar[ibit, :,:,0] = s1_ROI/s0_ROI
            bar[ibit, :,:,1] = s2_ROI/s0_ROI
            bar[ibit, :,:,2] = s3_ROI/s0_ROI
            
            if plot:
                self.im1.set_array(pol_in_ROI)
                self.im2.set_array(depol_in_ROI)
                self.im3.set_array(max_values)
            
                self.axs[0].set_title(f'Average pol angle: {np.mean(pol_in_ROI):.2f}')
                self.axs[2].set_title(f'Max intensity: {mvalue:.3e}', color = 'red' if mvalue > 0.9 else 'black')  # Update the title
                self.fig.suptitle(f'Bit: {bits[ibit]}')
                
                plt.draw()  # Redraw the figure
                plt.pause(0.2)  # Pause for 0.2 second
        
        #Close the plot at the end
        if plot:
            plt.ioff()  # Turn off interactive mode
            plt.close()

        # Flush to disk to ensure data is saved
        bar.flush()
        print('Scanning of the range complete.')




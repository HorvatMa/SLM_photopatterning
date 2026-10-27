# -*- coding: utf-8 -*-
"""
Created on Wed Dec  6 15:01:01 2023

@author: Anej
"""

import tkinter as tk
from PIL import Image, ImageTk
from tkinter import colorchooser
from itertools import cycle
import numpy as np
import io
import os
import cv2 


class ImageSelectorApp:
    '''
    How to use: 
        - You move the picture around with your right mouse button and drag
        - You can zoom on picture with your scroll wheel
        - You can select rectangles and name them by making a rectangle with your
        left mouse button and then pressing 'Enter'.
       - Program then saves their names into dictionary. If no name is chosen a stock name is generated.
       - You must close the program with the dedicated close and save rectangles button. 
        - CAREFUL! If you move the image outside the canvas scope, image gets reset to stock coordinates
        and all rectangles are deleted (this was hardcoded, cause I need to add the functionality
                                        of deleting objects hand by hand)
        - In the left corner you can see the top left and bottom right coordinates of current selection.
        - If you get an error of not able to find the picture, try reseting the console..
    '''
    def __init__(self, root, image):
        self.root = root
        self.root.title("Image Selector")

        # Load the image
        # Step 3: Apply a colormap using OpenCV (for example, COLORMAP_JET)
        colored_img = cv2.applyColorMap(image, cv2.COLORMAP_VIRIDIS)
        
        # Step 4: Convert the colormapped image (BGR format) to RGB format
        colored_img_rgb = cv2.cvtColor(colored_img, cv2.COLOR_BGR2RGB)
        


        self.original_image = Image.fromarray(colored_img_rgb )

        #Zato da imaš kopijo originala, ki ga lahko zoomaš
        self.image = self.original_image.copy()
        
        # Calculate initial zoom factor to fit the image on the screen
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        #What percentage of the screen do you want by default
        screen_factor = 0.8
        
        initial_zoom_x = screen_factor*screen_width / self.image.width
        initial_zoom_y = screen_factor*screen_height / self.image.height
        
        # Nastavi zaceten zoom factor
    
        self.zoom_factor = min(initial_zoom_x, initial_zoom_y)
       
        # Resize the image
        new_width = int(self.image.width * self.zoom_factor)
        new_height = int(self.image.height * self.zoom_factor)
        self.image = self.image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                                
        self.photo = ImageTk.PhotoImage(self.image)

        # Create paned window
        self.paned_window = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        #Old pack method
        # self.paned_window.pack(expand=True, fill=tk.BOTH)
        
        #Grid method
        self.paned_window.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)


        # Create canvas
        self.canvas = tk.Canvas(self.paned_window, width=self.photo.width(), height=self.photo.height())
        self.paned_window.add(self.canvas)
        

        # Display the image on the canvas
        self.image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        # Variables to store rectangle coordinates
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None

        # Variables for moving the image
        self.start_move_x = None
        self.start_move_y = None
        self.moving = False

        #How far away from initial spot you are (for moving the image) - offset
        self.offset_x = 0
        self.offset_y = 0
        
        
        # List to store rectangles coordinates, color and name
        self.rectangles = {}
        
        # List to store rectangle objects on the canvas
        self.rectangle_objects = []
        
        # To keep the number of the rectangles
        self.rectangles_number = 0

        
        # Bind mouse events
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Return>", self.on_enter)  # Bind Enter key event
        self.root.bind("<MouseWheel>", self.on_mousewheel)  # Bind mouse wheel event FOR ZOOMING
        
        # To je za pan opcijo
        self.canvas.bind("<B3-Motion>", self.on_right_drag)  # B3 means right mouse button
        self.canvas.bind("<ButtonPress-3>", self.on_right_press)
        self.canvas.bind("<ButtonRelease-3>", self.on_right_release)
        
        # Zoom factor
        # self.zoom_factor = 1.0

        # How many times have you pressed the right button (to clear the rectangle)
        self.times_pressed = 0
        
        # Create a frame for buttons
        self.button_frame = tk.Frame(root)
        self.button_frame.grid(row=0, column=1, sticky=tk.NE, padx=5, pady=5)

        # Create a button to finish on the bottom and close
        self.finish_button = tk.Button(self.button_frame, text="Close and \n save rectangles",\
                                       bg = 'red', fg = 'white', command=self.finish_and_close,\
                                       height= 2, width=15)
        self.finish_button.grid(row=1, column=0, sticky=tk.NE)
        

        # Create a button to save the image
        self.save_button = tk.Button(self.button_frame, text="Save",\
                                     bg = 'blue', fg = 'white', command=self.save_image,\
                                     height= 2, width=15)
        self.save_button.grid(row=0, column=0, sticky=tk.NE)
        
        #Cycle colors
        self.colors = cycle(["red", "blue", "green", "orange", "purple"])
        self.current_color = 'red'
        
        # Text box to display coordinates
        self.coordinates_text = tk.StringVar()
        self.coordinates_label = tk.Label(root, textvariable=self.coordinates_text)
        self.coordinates_label.place(relx=0., rely=0., anchor=tk.NW)
        
        

        # Bind the closing event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def on_closing(self):
       # Add any cleanup or confirmation logic here
       self.root.destroy()
       
    def save_image(self):
        
        # Save the current state of the canvas, including the image and rectangle coordinates
        save_name = tk.simpledialog.askstring("Input", "Enter the name of the save file full path (example: C:/Anej/LC.png)")
        
        if save_name:
            # Save the canvas content as an image
            eps = self.canvas.postscript(colormode="color")
            
            # use PIL to convert to PNG 
            im = Image.open(io.BytesIO(bytes(eps,'ascii')))
            im.save(os.path.join(save_name))
    
            print("Saved canvas!")

    
    def on_right_drag(self, event):
        if self.moving:
            # print(event.x, self.start_move_x)
            delta_x = event.x - self.start_move_x
            delta_y = event.y - self.start_move_y
            
            #Update the offset from the initial position
            self.offset_x += delta_x
            self.offset_y += delta_y
            
            
            # Move the image on the canvas
            self.canvas.move(self.image_id, delta_x, delta_y)
    
            self.start_move_x = event.x
            self.start_move_y = event.y  

                
            # Redraw rectangles
            for rect_name, values in self.rectangles.items():
                xt,yt = values['top left']
                xb, yb = values['bottom right']
                rect_coord = (xt,yt,xb,yb)


                # rect_coord = [x*self.zoom_factor for x in rect_coord]
                rect_coord =  self.scale_cord_to_offset(rect_coord)

                rect_color = values['color']
                
                rect_name = rect_name
                
                # Delete previous rectangles
                self.canvas.delete(rect_name)

                # Redraw the same rectangle
                self.canvas.create_rectangle(
                    rect_coord[0], rect_coord[1], rect_coord[2], rect_coord[3], outline=rect_color, tags=rect_name
                )
            
            # Reset the image back to the middle of the canvas
            img_x, img_y = self.canvas.coords(self.image_id)
            img_width = self.image.width
            img_height = self.image.height
            
            canvas_width = self.canvas.winfo_width()
            canvas_height =  self.canvas.winfo_height()
            
            crossed = False
            # If the image crosses the end of the canvas, reset it to the middle
            if img_x + 0.05*img_width > canvas_width:
                self.canvas.move(self.image_id, -img_x, -img_y)
                crossed  = True

            elif  img_y + 0.05*img_height > canvas_height:
                self.canvas.move(self.image_id, -img_x, -img_y)
                crossed  = True
                
            elif img_x < - 0.95*img_width:
                self.canvas.move(self.image_id, -img_x, -img_y)
                crossed  = True
                
            elif img_y <  -0.95*img_height:
                self.canvas.move(self.image_id, -img_x, -img_y)
                crossed  = True
            
            if crossed:
                # Delete rectangles
                for rect_name, values in self.rectangles.items():
                    # Delete previous rectangles
                    self.canvas.delete(rect_name)
                    self.rectangles = {}
                
    def on_right_release(self, event):
        self.moving = False     
        
    def on_right_press(self, event):
        self.start_move_x = event.x
        self.start_move_y = event.y
        self.moving = True
        
        
        
    def on_press(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)

        # This part of code is here. So you can click again to remove the rectangle drawn.
        self.times_pressed += 1
        
        if self.times_pressed == 2:
            # Delete drawing rectangle
            self.canvas.delete("rectangle")
            self.times_pressed = 0
            

    def on_drag(self, event):
        self.end_x = self.canvas.canvasx(event.x)
        self.end_y = self.canvas.canvasy(event.y)

        # Delete previous rectangles
        self.canvas.delete("rectangle")

        # Draw a new rectangle
        self.current_rectangle = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.end_x, self.end_y, outline="red", tags="rectangle"
        )
        
        coord = (self.start_x, self.start_y, self.end_x, self.end_y)
        coord_trans = self.scale_coord_to_og(coord)
        
        #Round up, so you have a nicer text ( not a lot of decimals..)
        ct_trun = [float(f'{c:2g}') for c in coord_trans] 
        self.coordinates_text.set(f"Coordinates: ({ct_trun[0]}, {ct_trun[1]})- ({ct_trun[2]}, {ct_trun[3]}),\
                                  širina: {int(np.abs(ct_trun[0]-ct_trun[2]))} px, višina: {int(np.abs(ct_trun[1]-ct_trun[3]))} px")
                                      
        
        

    def on_release(self, event):
        # This function will be called when the mouse button is released
        pass
    
    def scale_coord_to_og(self, coord):
        # Scale coordinates of a rectangle from offset position to original position
        # coord is a tuple of 4 values
            stx, sty, endx, endy = coord
            original_start_x = (stx - self.offset_x) / self.zoom_factor
            original_start_y = (sty - self.offset_y )/ self.zoom_factor
            original_end_x = (endx - self.offset_x) / self.zoom_factor
            original_end_y = (endy - self.offset_y)/ self.zoom_factor
            
            return (original_start_x, original_start_y, original_end_x, original_end_y)
        
    def scale_cord_to_offset(self, coord):
        # Scale coordinates of a rectangle from og position to offset position
        # coord is a tuple of 4 values
            stx, sty, endx, endy = coord
            scaled_stx = stx*self.zoom_factor +  self.offset_x
            scaled_sty = sty*self.zoom_factor  +  self.offset_y
            scaled_endx = endx*self.zoom_factor  +  self.offset_x
            scaled_endy  = endy*self.zoom_factor  +  self.offset_y
            
            return (scaled_stx, scaled_sty,scaled_endx, scaled_endy)  
        
        
    def on_enter(self, event):
        # Add the current rectangle object to the list
        if self.start_x is not None and self.start_y is not None and self.end_x is not None and self.end_y is not None:
            
            #Increase number by 1
            self.rectangles_number += 1 
            # Whats the number of the rectangle
            rectangle_num = self.rectangles_number
            
            #Append rectangle object
            self.rectangle_objects.append(self.current_rectangle)

            # Change to other coordinates with this scale_coord function
            rectangle_coords =  self.scale_coord_to_og((self.start_x, self.start_y, self.end_x, self.end_y))
            
            #What's the name of rectangle
            rectangle_name = tk.simpledialog.askstring("Input", "Enter the name for the rectangle (without spaces):")
            

        
            #If the string is empty, then put a trivial name by number
            if not rectangle_name:
                rectangle_name = f'Rectangle_{self.rectangles_number}'
                
            else:
                if " " in rectangle_name:
                    print('Space maš v imenu! Sem ga odstranil.')
                    rectangle_name  = rectangle_name.replace(" ", "")
                
            # COLOR 
            self.current_color = next(self.colors)
            
            # APPEND THE DATA TO DICTIONARY
            self.rectangles[rectangle_name] = {'top left': (rectangle_coords[0], rectangle_coords[1]),\
                                              'bottom right': (rectangle_coords[2], rectangle_coords[3]),\
                                              'color': self.current_color  
                                              }
            
            
            self.current_rectangle = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.end_x, self.end_y, outline=self.current_color, tags=rectangle_name)
            
            
            print("Rectangle Coordinates:", rectangle_coords)
            
            
            
    def finish_and_close(self):
        # Print or save the final coordinates when finishin
        for idx, (rect_name,values) in enumerate(self.rectangles.items(), start=1):
                start_xy = values['top left']
                end_xy = values['bottom right']
                print(f"Rectangle {idx + 1}: Top-left {start_xy}, Bottom-right {end_xy}")
        # Close the window
        self.root.destroy()
    
    def on_mousewheel(self, event):
        # Zoom in or out based on mouse wheel movement
        delta = event.delta
        if delta > 0:
            self.zoom_factor *= 1.1  # Zoom in
        else:
            self.zoom_factor /= 1.1  # Zoom out
    
        # Resize the image and update the canvas
        self.image = self.original_image.copy()
        new_width = int(self.image.width * self.zoom_factor)
        new_height = int(self.image.height * self.zoom_factor)
        self.image = self.image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(self.image)
        self.canvas.itemconfig(self.image_id, image=self.photo)
    
        # Redraw rectangles
        for rect_name, values in self.rectangles.items():
            xt,yt = values['top left']
            xb, yb = values['bottom right']
            rect_coord = (xt,yt,xb,yb)


            # rect_coord = [x*self.zoom_factor for x in rect_coord]
            rect_coord =  self.scale_cord_to_offset(rect_coord)

            rect_color = values['color']
            
            rect_name = rect_name
            
            # Delete previous rectangles
            self.canvas.delete(rect_name)

            # Redraw the same rectangle
            self.canvas.create_rectangle(
                rect_coord[0], rect_coord[1], rect_coord[2], rect_coord[3], outline=rect_color, tags=rect_name
            )
        
        

    # PRIMER
# =============================================================================
#     
#     # Da dobiš objekte kličeš app.rectangles. V njem je nested dictionary oblike
#     # app.rectangles['ime_pravokotnika'] = {'top left': (top_x_coordinate , top_y_coordinate),\
#     #                                   'bottom right': (bottom_x_coordinate, bottom_y_coordinate),\
#     #                                   'color': barva 
#     #                                   }
#    
#     
#     #Klicimo rectangle knjiznico, ki smo jih generirali
#     dicto = app.rectangles
# 
#     # Poglej zgornjo koordinato prvega pravokotnika 
#     first_key = [key for key in dicto.keys()][0]
#     top_right_koord = dicto[first_key]['top left']
#     print('top left koordinati sta', top_right_koord)
# 
# =============================================================================


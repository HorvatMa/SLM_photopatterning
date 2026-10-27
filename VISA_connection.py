# -*- coding: utf-8 -*-
"""
Created on Tue Dec 24 09:20:41 2024

@author: Anej/Andrej
"""


import time
import pyvisa as visa


DEVICES = ['ITC4020']   #THORLABS controllers. Currently we only have one.


_LD_CONFIG_DEFAULT = {                 
        "polarity" : 0,                             # 0 for Cathode-Ground
        "switchon_delay" : 1.,                      # float, LD switch on delay in seconds 
        "voltage_protection" : 5.5,                  # float, Voltage protection
        "laser_current_limit" : 1.55,                # float, maximum current
        }




def returnport(ports, keyword = 'M00248415'):
    for i, port in enumerate(ports):
        if keyword in port:
            print(port)
            return port
        

            

class LaserController():
    """This is a VISA controller for the THORLABS diode controller.
    It uses the visa module for IO. You can of course still use raw
    commands by calling :meth:`~.THORLABSLaserController.ask` or meth:`~.THORLABSLaserController.write`
    for a more custom control.
    
    Examples
    --------
    First you must initialize the controller. For automatic address determination
    do
    
    >>> fg = LaserController()
    >>> fg.init()
  
    If you know the address of your device, you can specify
    
    >>> fg.init(address = 'GPIB0::12')
    
    or
    
    >>> fg.address = 'GPIB0::12'
    
    Now  you can set the parameters for you current or voltage.
    
    
    
    Of course you can send raw commands:
    
    >>> fg.write('VOLT 1 VPP')
    
    You shuld call the check_errorb to check if any errors accured during the 
    transmission. It will raise an exception if error appears.
    
    >>> fg.check_error()
    
    When done do not forget to close the connection (and turn output off)
    
    >>> fg.off()
    >>> fg.close()
    """


    def init(self, address = None, findstr = 'M00248415', timeout = 1):
        
        #Initialize the resource manager
        rm = visa.ResourceManager()
        if address is None:
            #List resources
            ports = rm.list_resources()
            
            if not ports:
                print('There is no resources')
                
            wanted_address = returnport(ports, keyword = findstr)
            
            if address == '':
                print(f'The resource with string {findstr} was not found.')
            
        else:
            wanted_address = address
            
        self.instrument = rm.open_resource(wanted_address, timeout = timeout * 1000) 
        self._address = wanted_address
        self._info = self.instrument.query('*IDN?')
        self._initialized = True
        
        #Initialize what the beginning state is
        self.current_state()
        
        
        
        
    def setup(self):
        
        #Setup the initial values for the diode controller
        c=_LD_CONFIG_DEFAULT

        self.set_voltage_protection(c['voltage_protection'])
        self.set_current_limit(c['laser_current_limit'])


    def set_voltage_protection(self, value):
        self.instrument.write('OUTP:PROT:VOLT {}'.format(value))
        print('LD voltage protection set to {} V.'.format(value))
        
    def set_current_limit(self,value):
        self.instrument.write('SOUR:CURR:LIM {}'.format(value))
        print('Current limit set to {} A.'.format(value))

    def ld_on(self):
        print('LD ON.')
        self.instrument.write('OUTP ON')
        
    def ld_off(self):
        print('LD OFF.')
        self.instrument.write('OUTP OFF')
        
    def current_state(self):
        self.state = self.instrument.query('OUTP?')
        print(f'Current state is {self.state}')
        
    def set_current(self,value):
        self.instrument.write('SOUR:CURR {}'.format(value))
        print('Current set to {} A.'.format(value))
        
    def get_current(self):
        self.cur_current  =self.instrument.query('SOUR:CURR?')
        print('The current is now {} A.'.format(self.cur_current))
        return self.cur_current
        
        
    def close(self):
        self.instrument.close()
        print('LD driver connection closed.')
    
                
            


# fg = LaserController()
# fg.init()
# fg.setup()




















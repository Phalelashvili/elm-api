import time
import serial
import queue
import logging
import threading
from structs import *


#   TODO: huge performance boost
#   tasks requiring more than 1 command can be sped up by
#   not sending every command separately. instead, buffer commands
#   and once every required command is in the buffer, send them together
#   this will minimize the communication delay between pc and elm
#   responses would have to go through some processing as well


class ELM(threading.Thread):
    def __init__(self, serialPort: str, baudrate=9600):
        '''initialize class and serial connection
        Args:
            serialPort (str): COMx for Windows, /dev/ttyUSBx for Unix
            baudrate (int): baudrate, duh
        '''
        super().__init__()
        self._running = True

        self._serial = serial.Serial(serialPort, baudrate)
        self.protocol = 0
        self.monitoring = False
        self._processing_command = False
        self._recv_buffer = queue.Queue()
        self._header = None

        # start thread
        self.start()

        # reset elm
        self.reset()

    def run(self):
        '''polls data from serial and calls _process_data'''
        msg = bytearray()
        while self._running:
            
            try:
                char = self._serial.read(1)
            except:
                if self._running:
                    raise
            # if we're in monitoring mode, there is no > after response
            # messages are separated by \r
            stopChar = b'\r' if self.monitoring else b'>'
            msg += char
            if char != stopChar:
                continue

            # too much data to log
            if not self.monitoring:
                logging.debug(f'{time.time(): <18} response {msg}')

            self._recv_buffer.put(msg)
            msg = bytearray()

            if self.monitoring:
                self._process_data()

            time.sleep(0.0001)

    def stop(self):
        '''stops self.run thread'''
        self._running = False
        self._serial.close()

    def execute(self, command, resumeMA=True, waitForResponse=True, **kwargs):
        '''calls self.executeMany with single command'''
        return self.executeMany([command], resumeMA=resumeMA, waitForResponse=waitForResponse, **kwargs)

    def executeMany(self, commands: list, resumeMA=True, waitForResponse=True):
        '''writes CR appended command to serial

        Args:
            commands (list of str): commands to execute
            resumeMA (bool): starts ATMA command again if self.monitoring
        Returns:
            response to command (str): returns 'SKIPPED' if !waitForResponse
        '''
        resumeMonitoring = resumeMA and self.monitoring
        
        if resumeMonitoring:
            self.stopMonitorAll()

        self._processing_command = True
        
        for command in commands:
            command = f'{command}\r'.encode()
            self._serial.write(command)
            logging.debug(f"{time.time(): <18} executing {command} ({resumeMA}, {waitForResponse})")
            
            resp = self._drawResponse() if waitForResponse else 'SKIPPED'

        self._processing_command = False
        if resumeMonitoring:
            self.monitorAll(self._monitor_callback)

        return resp


    def _process_data(self):
        '''this function is called by _recv_data thread'''
        data = self._drawResponse()
        
        # too much work for these messages to filter before it gets here
        # just hardcoding filter is good enough for now
        for i in [b'ATMA\r']:
            if data == i:
                return

        if not self._processing_command: # if false, self.execute should draw the response
            self._monitor_callback(bytes(data[:-1]))

    #---------------------------------------------------------------------------
    # AT Commands
    # https://www.elmelectronics.com/wp-content/uploads/2016/07/ELM327DS.pdf
    #---------------------------------------------------------------------------

    def setProtocol(self, protocol):
        '''sets OBD protocol

        Args:
            protocol (int): value from structs.Protocol
        '''
        self.execute('ATSP' + str(protocol))
        self.protocol = protocol
        self._header = None

    def setHeader(self, header):
        '''set header for message. if header is same as previous header, skip

        Args:
            header (str/int): header in hexstring (w/o 0x)
            OR int, which will be converted to hexstring
        '''
        if type(header) == int:
            header = hex(header)[2:]
        else:
            header = header.replace(' ', '')

        if header == self._header:
            logging.debug(f'{time.time(): <18} header already set to {header}')
            return
        self._header = header

        try:
            int(header, 16)
            #TODO: check length
        except:
            raise Exception('Header must be HEX')
        self.execute('ATSH ' + header)

    def setHeaderAndSend(self, header: str, message: str):
        '''set header and send message
        Args:
            header (str): header to hexstring (w/o 0x)
            message (str): header to hexstring (w/o 0x)
        '''
        header = header.replace(' ', '')
        try:
            int(header, 16)
            #TODO: check length
        except:
            raise Exception('Header must be hexstring')
        self.executeMany(['ATSH ' + header, message])

    def send(self, message: str):
        '''sends message to vehicle.
        use setProtocol and setHeader before sending
        
        Args:
            message (str): header to hexstring (w/o 0x)
        Returns:
            bool: can't tell if message was successfully sent
            when auto-receive is disabled. returns True if 
            elm understood message (didn't send questionmark) 
        '''
        message = message.replace(' ', '')
        try:
            int(message, 16)
            #TODO: check length
        except:
            raise Exception('Message must be hexstring')

        if b'?' in self.execute(message):
            return False
        return True

    def monitorAll(self, callback):
        '''monitors/listens all protocols
        Args:
            callback (fn): function to be called on new data
        '''
        self._monitor_callback = callback

        if self.monitoring:
            logging.debug('ATMA already running, skipping execution')
            return

        self.monitoring = True
        self.execute('ATMA', resumeMA=False, waitForResponse=False)

    def stopMonitorAll(self):
        '''stops ATMA command'''
        # this should be set to false before executing
        # so that self.run will know what to expect from response
        self.monitoring = False

        # any len(command) > 1 will cancel ATMA
        self.execute('', resumeMA=False)

    def reset(self, waitForBoot=True):
        '''resets elm device from software
        Args:
            waitForBoot (bool): function will not return until device finishes boot
        '''
        self.monitoring = False
        self._header = None
        self.execute(' ') # stash command in progress if any
        #NOTE: do not send just \r. that means executing previous command

        self.execute('ATWS', waitForResponse=waitForBoot)

        # spaces must be off for responses to be detected properly
        self.execute('ATS0')
        # automatic responses slow communication down.
        # use self.monitorAll for receiving messages
        self.execute('ATR0')


    def _drawResponse(self):
        '''Returns: next response from ELM recv buffer'''
        return self._recv_buffer.get()

    ### secondary AT commands ###

    def setHeaderState(self, state: int):
        '''printing of headers off*, or on
        Args:
            state (bool): True or False
        '''
        self.execute(f'ATH{int(state)}')

    def allowLongMessages(self):
        '''Allow Long (>7 byte) messages'''
        self.execute('ATAL')

    def setBaudrate(self, baudrate: int):
        '''sets baudrate from PRESELECTED values
        Args:
            baudrate (Structs.Baudrates)
        '''

        self.execute(f'ATPP 0C SV {baudrate}')
        self.execute('ATPP 0C ON')
        self.reset()
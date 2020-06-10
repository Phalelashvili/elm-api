import time
import serial
import queue
import logging
import threading

class ELM(threading.Thread):
    def __init__(self, serialPort: str, baudrate=9600):
        '''initialize serial connection
        Args:
            serialPort (str): COMx for Windows, /dev/ttyUSBx for Unix
            baudrate (int): baudrate, duh
        '''
        super().__init__()
        self._running = True

        self._serial = serial.Serial(serialPort, baudrate)
        self.protocol = 0
        self._monitoring = False
        self._processing_command = False
        self._recv_buffer = queue.Queue()
        self._header = None

        # start thread
        self.start()
        
        # reset elm
        self.reset()

        # echo and spaces must be off for responses to be detected properly
        self.execute('ATE0')
        self.execute('ATS0')


    def run(self):
        '''polls data from serial and calls _process_data'''
        while self._running:
            # response ends with ">".            strip away \r\r>
            data = self._serial.read_until(b'>')[:-3]
            self._recv_buffer.put(data)
            
            if self._monitoring:
                self._process_data()

            time.sleep(0.0001)

    def stop(self):
        self._running = False

    def execute(self, command, **kwargs):
        '''calls self.executeMany'''
        self.executeMany([command], **kwargs)

    def executeMany(self, commands: list, resumeMA=True, waitForResponse=True):
        '''writes CR appended command to serial
        Args:
            commands (list of str): commands to execute
            resumeMA (bool): starts ATMA command again if self._monitoring
        Returns:
            response to command (str): returns 'SKIPPED' if !waitForResponse
        '''
        resumeMonitoring = resumeMA and self._monitoring
        
        if resumeMonitoring:
            self.stopMonitorAll()

        self._processing_command = True
        
        for command in commands:
            command = f'{command}\r'.encode()
            self._serial.write(command)
            logging.debug(f"{time.time(): <18} executing {command}")
            
            resp = self._drawResponse() if waitForResponse else 'SKIPPED'
            logging.debug(f'{time.time(): <18} {command} got response {resp}')

        self._processing_command = False

        if resumeMonitoring:
            self.monitorAll(self._monitor_callback)

        return resp


    def _process_data(self):
        '''this function is called by _recv_data thread'''
        data = bytes.fromhex(self._drawResponse())
        if not self._processing_command: # if false, self.execute should draw the response
            self._monitor_callback(data)

    #---------------------------------------------------------------------------
    # AT Commands
    # https://www.elmelectronics.com/wp-content/uploads/2016/07/ELM327DS.pdf
    #---------------------------------------------------------------------------

    def setProtocol(self, protocol):
        raise NotImplementedError()
        #TODO
        self.protocol = protocol

    def setHeader(self, header: str):
        '''set header for data. if header is same as previous header, skip

        Args:
            header (str): header to HEX string (w/o 0x)
        '''
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

    def setHeaderAndSend(self, header: str, data: str):
        '''set header and send data
        Args:
            header (str): header to HEX string (w/o 0x)
            data (str)
        '''
        header = header.replace(' ', '')
        try:
            int(header, 16)
            #TODO: check length
        except:
            raise Exception('Header must be HEX')
        self.executeMany(['ATSH ' + header, data])

    def monitorAll(self, callback):
        '''monitors/listens all protocols
        Args:
            callback (fn): function to be called on new data
        '''
        self._monitor_callback = callback

        if self._monitoring:
            logging.warning('ATMA already running, skipping execution')
            return
        self.execute('ATMA', waitForResponse=False)
        self._monitoring = True

    def stopMonitorAll(self):
        '''stops ATMA command'''
        self._monitoring = False
        
        # any len(command) > 1 will cancel ATMA
        self.execute('', resumeMA=False)

    def reset(self, waitForBoot=True):
        '''resets elm device from software
        Args:
            waitForBoot (bool): function will not return until device finishes boot
        '''
        self._monitoring = False
        self._header = None
        self.execute('') # stash whatever command was in progress
        self.execute('ATWS', waitForResponse=waitForBoot)

    def _drawResponse(self):
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
        '''(only for STN chips) sets baudrate from PRESELECTED values
        Args:
            baudrate (int): 19200, 38400, 57600, 115200, 230400 or 500000
        '''
        mapping = {
            # missing baudrates
            19200   : 'D0',
            38400   : '68',
            57600   : '45',
            115200  : '23',
            230400  : '11',
            500000  : '08',
            2000000 : '02'
        }
        
        if baudrate not in mapping:
            raise Exception('Invalid baudrate')

        self.execute('ATPP 0C SV '+ mapping.get(baudrate))
        self.execute('ATPP 0C ON')
        self.reset()
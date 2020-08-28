import time
from typing import List, Union
import serial
import queue
import logging
import threading

logger = logging.getLogger("OBD")


class ELM(threading.Thread):

    def __init__(self, serial_port: str, baudrate=9600):
        """initialize class and serial connection
        Args:
            serial_port (str): COMx for Windows, /dev/ttyUSBx for Unix
            baudrate (int): baudrate, duh
        """
        super().__init__()
        self._running = True

        self._serial = serial.Serial(serial_port, baudrate)
        self.protocol = 0
        self.monitoring = False
        self._processing_command = False
        self._monitor_callback = None
        self._recv_buffer = queue.Queue()
        self._header = None
        self.data_byte = '--'

        # start thread
        self.start()

        # reset elm
        self.reset()

        # ELM allows 1 byte storage, FF by default
        self.data_byte = self.execute('AT RD').decode().split('\r')[1]

    def run(self):
        """polls data from serial and calls _process_data"""
        msg = bytearray()
        while self._running:
            try:
                char = self._serial.read(1)
            except:
                if self._running:
                    raise
                return
            # if we're in monitoring mode, there is no > after response
            # messages are separated by \r
            stop_char = b'\r' if self.monitoring else b'>'
            msg += char
            if char != stop_char:
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
        """stops self.run thread"""
        self._running = False
        self._serial.close()

    def execute(self, command, resume_ma=True, wait_for_response=True) -> bytes:
        """calls self.execute_many with single command"""
        return self.execute_many([command], resume_ma=resume_ma, wait_for_response=wait_for_response)

    def execute_many(self, commands: List[str], resume_ma=True, wait_for_response=True) -> bytes:
        """writes CR appended command to serial

        Args:
            commands (list of str): commands to execute
            resume_ma (bool): starts ATMA command again if self.monitoring
            wait_for_response (bool): do not continue execution until we get response
        Returns:
            response to command (bytes): returns 'SKIPPED' if !wait_for_response
        """
        resume_monitoring = resume_ma and self.monitoring

        if resume_monitoring:
            self.stop_monitor_all()

        self._processing_command = True

        resp = bytes()
        for command in commands:
            command = f'{command}\r'.encode()
            self._serial.write(command)
            logging.debug(f"{time.time(): <18} {self.data_byte} executing {command} ({resume_ma}, {wait_for_response})")

            resp = self._draw_response() if wait_for_response else 'SKIPPED'

        self._processing_command = False
        if resume_monitoring:
            self.monitor_all(self._monitor_callback)

        return resp

    def _process_data(self) -> None:
        """this function is called by _recv_data thread"""
        data = self._draw_response()

        # too much work for these messages to filter before it gets here
        # just hard-coding filter is good enough for now
        for i in [b'ATMA\r']:
            if data == i:
                return

        if not self._processing_command:  # if false, self.execute should draw the response
            self._monitor_callback(data[:-2])

    def close(self):
        """closes serial communication"""
        self._serial.close()

    # ---------------------------------------------------------------------------
    # AT Commands
    # https://www.elmelectronics.com/wp-content/uploads/2016/07/ELM327DS.pdf
    # ---------------------------------------------------------------------------

    def set_protocol(self, protocol) -> None:
        """sets OBD protocol

        Args:
            protocol (int): value from structs.Protocol
        """
        self.execute('ATSP' + str(protocol))
        self.protocol = protocol
        self._header = None

    def set_header(self, header) -> None:
        """set header for message. if header is same as previous header, skip

        Args:
            header (str/int): header in hex-string (w/o 0x)
            OR int, which will be converted to hex-string
        """
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
            # TODO: check length
        except:
            raise Exception('Header must be HEX')
        self.execute('ATSH ' + header)

    def send_with_header(self, header: Union[str, int], message: str) -> None:
        """set header and send message

        Args:
            header (Union[str, int]): can be HEX value of header or hex-string (without "0x")
            message (str): hex-string of message (without "0x")
        """
        if type(header) == int:
            header = hex(header)[2:]
        else:
            header = header.replace(' ', '')

        if header == self._header:
            logging.debug(f'{time.time(): <18} header already set to {header}')

        try:
            int(header, 16)
            # TODO: check length
        except:
            raise Exception('Header must be HEX')

        message = message.replace(' ', '')
        try:
            int(message, 16)
            # TODO: check length
        except:
            raise Exception('Message must be hex-string')

        self.execute_many(['ATSH ' + header, message])

    def send(self, message: str) -> bool:
        """sends message to vehicle.
        use set_protocol and set_header before sending

        Args:
            message (str): header to hex-string (w/o 0x)
        Returns:
            bool: True if msg was sent successfully.
            (when elm doesn't send "?" or error)
        """
        message = message.replace(' ', '')
        try:
            int(message, 16)
            # TODO: check length
        except:
            raise Exception('Message must be hex-string')

        r = self.execute(message)
        if b'?' in r or b'ERROR' in r:
            return False
        return True

    def monitor_all(self, callback) -> None:
        """monitors/listens all protocols
        Args:
            callback (fn): function to be called on new data
        Callback:
            each message received from ATMA command
            takes single argument, passes byte encoded message
            separated by spaces like 123 01 02 03 04 05
            (header and msg indexes depend on protocol)
        """
        self._monitor_callback = callback

        if self.monitoring:
            logging.debug('ATMA already running, skipping execution')
            return

        self.monitoring = True
        self.execute('ATMA', resume_ma=False, wait_for_response=False)

    def stop_monitor_all(self):
        """stops ATMA command"""
        # this should be set to false before executing
        # so that self.run will know what to expect from response
        self.monitoring = False

        # any command with length >= 1 will cancel ATMA
        self.execute('', resume_ma=False)
 
    def reset(self, wait_for_boot=True) -> None:
        """resets elm device from software

        Args:
            wait_for_boot (bool): function will not return until device finishes boot
        """
        self.monitoring = False
        self._header = None
        self.execute(' ')  # stash command in progress if any
        # NOTE: do not send just \r. that means executing previous command

        self.execute('ATWS', wait_for_response=wait_for_boot)

    def set_header_state(self, state: int) -> None:
        """printing of headers off*, or on
        Args:
            state (bool): True or False
        """
        self.execute(f'ATH{int(state)}')

    # ---------------------------------------------------------------------------
    # secondary AT commands
    # ---------------------------------------------------------------------------

    def _draw_response(self) -> bytes:
        """Returns: next response from ELM recv buffer"""
        return self._recv_buffer.get()

    def set_auto_receive(self, state: int) -> None:
        """set automatic receive (on by default)
        Args:
            state (bool): True or False
        """
        self.execute(f'ATR{int(state)}')

    def allow_long_messages(self) -> None:
        """Allow Long (>7 byte) messages"""
        self.execute('ATAL')

    def set_baudrate(self, baudrate: int) -> None:
        """sets baudrate from PRESELECTED values
        Args:
            baudrate (Structs.Baudrates)
        """

        self.execute(f'ATPP 0C SV {baudrate}')
        self.execute('ATPP 0C ON')
        self.execute('ATZ')  # hard reset
        # self.reset()

    def save_data_byte(self, data_byte: str) -> None:
        """it's self-explanatory"""
        self.data_byte = data_byte
        self.execute(f'AT SD {data_byte}')

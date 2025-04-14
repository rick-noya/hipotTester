import ctypes
import sys
import time
import os
import logging

# Import constants from the utils module
# Assuming utils package is in the python path or relative import works
from utils.constants import (
    VID, PID, DLL_PATH,
    HID_UART_STATUS, HID_UART_DEVICE, DWORD, WORD, BYTE, BOOL,
    HID_UART_SUCCESS, HID_UART_READ_TIMED_OUT,
    DEFAULT_BAUD_RATE, DEFAULT_READ_TIMEOUT_MS, DEFAULT_WRITE_TIMEOUT_MS,
    RESPONSE_READ_TIMEOUT_MS,
    HID_UART_EIGHT_DATA_BITS, HID_UART_NO_PARITY, HID_UART_SHORT_STOP_BIT,
    HID_UART_RTS_CTS_FLOW_CONTROL
)

class V7xDeviceError(Exception):
    """Custom exception for V7x device errors."""
    pass

class V7xDevice:
    """Handles communication with a Vitrek V7X device via SLABHIDtoUART DLL."""

    def __init__(self, debug=False, logger=None):
        self._dll = None
        self._device_handle = HID_UART_DEVICE(None)
        self._is_open = False
        self.debug = debug # Set to True for verbose output
        self._logger = logger # Optional external logger
        
        try:
            self._load_dll()
            self._define_functions()
            self._log_info(f"DLL Library Version: {self.get_library_version()}")
        except V7xDeviceError as e:
            self._log_error(f"Error initializing V7xDevice: {e}")
            # Allow object creation but it will be non-functional
            self._dll = None

    def set_logger(self, logger):
        """Set an external logger for the device."""
        self._logger = logger
        self._log_info("External logger attached to V7xDevice")

    def _log_info(self, message):
        """Log an info message to both console and logger if available."""
        print(message)
        if self._logger and hasattr(self._logger, 'info'):
            self._logger.info(f"V7xDevice: {message}")

    def _log_error(self, message):
        """Log an error message to both console and logger if available."""
        print(f"ERROR: {message}")
        if self._logger and hasattr(self._logger, 'error'):
            self._logger.error(f"V7xDevice: {message}")

    def _log_warning(self, message):
        """Log a warning message to both console and logger if available."""
        print(f"WARNING: {message}")
        if self._logger and hasattr(self._logger, 'warning'):
            self._logger.warning(f"V7xDevice: {message}")

    def _log_debug(self, message):
        """Log a debug message if debug is enabled and logger is available."""
        if self.debug:
            print(f"DEBUG: {message}")
            if self._logger and hasattr(self._logger, 'debug'):
                self._logger.debug(f"V7xDevice: {message}")

    def _load_dll(self):
        """Load the SLABHIDtoUART DLL."""
        if not os.path.exists(DLL_PATH):
            error_msg = f"DLL not found at path: {DLL_PATH}. Please check utils/constants.py"
            self._log_error(error_msg)
            raise V7xDeviceError(error_msg)
            
        try:
            self._dll = ctypes.WinDLL(DLL_PATH)
            self._log_info(f"Successfully loaded DLL: {DLL_PATH}")
        except OSError as e:
            error_msg = f"Error loading DLL from path: {DLL_PATH}. OSError: {e}"
            self._log_error(error_msg)
            raise V7xDeviceError(error_msg)

    def _define_functions(self):
        """Define ctypes function signatures for the DLL functions."""
        if not self._dll:
            raise V7xDeviceError("DLL not loaded, cannot define functions.")

        try:
            # GetNumDevices
            self._dll.HidUart_GetNumDevices.argtypes = [ctypes.POINTER(DWORD), WORD, WORD]
            self._dll.HidUart_GetNumDevices.restype = HID_UART_STATUS
            # Open
            self._dll.HidUart_Open.argtypes = [ctypes.POINTER(HID_UART_DEVICE), DWORD, WORD, WORD]
            self._dll.HidUart_Open.restype = HID_UART_STATUS
            # SetUartConfig
            self._dll.HidUart_SetUartConfig.argtypes = [HID_UART_DEVICE, DWORD, BYTE, BYTE, BYTE, BYTE]
            self._dll.HidUart_SetUartConfig.restype = HID_UART_STATUS
            # SetTimeouts
            self._dll.HidUart_SetTimeouts.argtypes = [HID_UART_DEVICE, DWORD, DWORD]
            self._dll.HidUart_SetTimeouts.restype = HID_UART_STATUS
            # Write
            self._dll.HidUart_Write.argtypes = [HID_UART_DEVICE, ctypes.POINTER(BYTE), DWORD, ctypes.POINTER(DWORD)]
            self._dll.HidUart_Write.restype = HID_UART_STATUS
            # Read
            self._dll.HidUart_Read.argtypes = [HID_UART_DEVICE, ctypes.POINTER(BYTE), DWORD, ctypes.POINTER(DWORD)]
            self._dll.HidUart_Read.restype = HID_UART_STATUS
            # Close
            self._dll.HidUart_Close.argtypes = [HID_UART_DEVICE]
            self._dll.HidUart_Close.restype = HID_UART_STATUS
            # FlushBuffers
            self._dll.HidUart_FlushBuffers.argtypes = [HID_UART_DEVICE, BOOL, BOOL]
            self._dll.HidUart_FlushBuffers.restype = HID_UART_STATUS

            # GetLibraryVersion (Optional)
            try:
                self._dll.HidUart_GetLibraryVersion.argtypes = [ctypes.POINTER(BYTE), ctypes.POINTER(BYTE), ctypes.POINTER(BOOL)]
                self._dll.HidUart_GetLibraryVersion.restype = HID_UART_STATUS
                self._has_version_api = True
            except AttributeError:
                self._has_version_api = False
                print("Warning: HidUart_GetLibraryVersion function not found in DLL.")

        except AttributeError as e:
            raise V7xDeviceError(f"Error accessing function in DLL: {e}. DLL might be incompatible or corrupted.")

    def get_library_version(self):
        """Get the DLL library version if the function exists."""
        if not self._dll or not self._has_version_api:
            return "Unknown (API not available)"

        major = BYTE(0)
        minor = BYTE(0)
        release = BOOL(0)
        status = self._dll.HidUart_GetLibraryVersion(ctypes.byref(major), ctypes.byref(minor), ctypes.byref(release))

        if status == HID_UART_SUCCESS:
            return f"{major.value}.{minor.value} (Release: {bool(release.value)})"
        else:
            return f"Error {status}"

    def find_device(self):
        """Check if a V7X device is connected and return the count."""
        if not self._dll: return 0
        num_devices = DWORD(0)
        status = self._dll.HidUart_GetNumDevices(ctypes.byref(num_devices), WORD(VID), WORD(PID))
        if status != HID_UART_SUCCESS:
            self._log_error(f"Error checking for devices: {status}")
            return 0
        if num_devices.value == 0:
            self._log_info(f"No V7X devices found with VID={VID:04x}, PID={PID:04x}")
        else:
            self._log_info(f"Found {num_devices.value} V7X device(s)")
        return num_devices.value

    def open(self, device_index=0):
        """Open a connection to the specified device index."""
        if not self._dll: 
            self._log_error("Cannot open device: DLL not loaded")
            return False
            
        if self._is_open:
            self._log_info("Device already open.")
            return True

        self._log_info(f"Attempting to open device at index {device_index}...")
        status = self._dll.HidUart_Open(ctypes.byref(self._device_handle), DWORD(device_index), WORD(VID), WORD(PID))
        if status != HID_UART_SUCCESS or not self._device_handle.value:
            self._log_error(f"Error opening device {device_index}: status code {status}")
            self._device_handle = HID_UART_DEVICE(None)
            return False

        self._is_open = True
        self._log_info(f"Device {device_index} opened successfully. Handle: {self._device_handle.value}")

        # Configure UART and Timeouts upon opening
        if not self._configure_uart(): 
            self._log_error("Failed to configure UART settings")
            self.close()
            return False
            
        if not self._set_timeouts(DEFAULT_READ_TIMEOUT_MS, DEFAULT_WRITE_TIMEOUT_MS): 
            self._log_error("Failed to set timeouts")
            self.close()
            return False
            
        if not self.flush_buffers(): 
            self._log_error("Failed to flush device buffers")
            self.close()
            return False

        self._log_info("Device fully configured and ready")
        return True

    def close(self):
        """Close the connection to the device."""
        if not self._is_open or not self._device_handle or not self._device_handle.value:
            self._is_open = False
            return True # Considered success if already closed
        if not self._dll:
            self._is_open = False
            return False # Cannot close if DLL isn't loaded

        status = self._dll.HidUart_Close(self._device_handle)
        self._device_handle = HID_UART_DEVICE(None) # Clear handle
        self._is_open = False

        if status == HID_UART_SUCCESS:
            print("Device closed successfully.")
            return True
        else:
            print(f"Error closing device: {status}")
            return False

    def _configure_uart(self, baud_rate=DEFAULT_BAUD_RATE, data_bits=HID_UART_EIGHT_DATA_BITS, parity=HID_UART_NO_PARITY, stop_bits=HID_UART_SHORT_STOP_BIT, flow_control=HID_UART_RTS_CTS_FLOW_CONTROL):
        """Configure the virtual UART settings."""
        if not self._is_open: return False
        status = self._dll.HidUart_SetUartConfig(
            self._device_handle,
            DWORD(baud_rate),
            BYTE(data_bits),
            BYTE(parity),
            BYTE(stop_bits),
            BYTE(flow_control)
        )
        if status != HID_UART_SUCCESS:
            print(f"Warning: Failed to configure UART (Baud: {baud_rate}): {status}")
            # return False # Decide if this is critical
        return True

    def _set_timeouts(self, read_ms, write_ms):
        """Set the read and write timeouts."""
        if not self._is_open: return False
        status = self._dll.HidUart_SetTimeouts(self._device_handle, DWORD(read_ms), DWORD(write_ms))
        if status != HID_UART_SUCCESS:
            print(f"Warning: Failed to set timeouts (Read: {read_ms}ms, Write: {write_ms}ms): {status}")
            # return False # Decide if critical
        return True

    def flush_buffers(self, flush_tx=True, flush_rx=True):
        """Flush the transmit and/or receive buffers."""
        if not self._is_open: return False
        status = self._dll.HidUart_FlushBuffers(self._device_handle, BOOL(flush_tx), BOOL(flush_rx))
        if status != HID_UART_SUCCESS:
            print(f"Warning: Failed to flush buffers (TX: {flush_tx}, RX: {flush_rx}): {status}")
            return False
        return True

    def send_command(self, command):
        """Send a command string, adding CR termination."""
        if not self._is_open: return False
        if not command.endswith('\r'):
            command += '\r'

        cmd_bytes = command.encode('ascii')
        # Create buffer from bytes, ensuring it's writable for ctypes
        cmd_buffer = (BYTE * len(cmd_bytes)).from_buffer_copy(cmd_bytes)
        bytes_written = DWORD(0)

        if self.debug: print(f"DEBUG TX: {command.strip()}")

        status = self._dll.HidUart_Write(
            self._device_handle,
            cmd_buffer,
            DWORD(len(cmd_bytes)),
            ctypes.byref(bytes_written)
        )

        if status != HID_UART_SUCCESS:
            print(f"Error sending command: {status}")
            return False
        if bytes_written.value != len(cmd_bytes):
            # This might happen with USB HID, might not be a fatal error
            print(f"Warning: Bytes written ({bytes_written.value}) != Command length ({len(cmd_bytes)})")

        return True

    def read_response(self, timeout_ms=RESPONSE_READ_TIMEOUT_MS):
        """Read response until LF or timeout."""
        if not self._is_open: return None
        response = ""
        read_buffer = (BYTE * 1)() # Read one byte at a time
        read_start_time = time.time()

        # Set a short polling timeout for individual reads
        poll_read_timeout_ms = 50
        self._set_timeouts(poll_read_timeout_ms, DEFAULT_WRITE_TIMEOUT_MS)

        while (time.time() - read_start_time) * 1000 < timeout_ms:
            bytes_read = DWORD(0)
            status = self._dll.HidUart_Read(self._device_handle, read_buffer, DWORD(1), ctypes.byref(bytes_read))

            if status == HID_UART_SUCCESS:
                if bytes_read.value == 1:
                    char_code = read_buffer[0]
                    if char_code == ord(b'\n'): # LF terminates response
                        break
                    if char_code != ord(b'\r'): # Ignore CR
                        response += chr(char_code)
                    # Reset timer slightly on successful read
                    # read_start_time = time.time() # Optional: reset timer fully?
                else:
                    # No data read in this poll, yield briefly
                    time.sleep(0.01)
            elif status == HID_UART_READ_TIMED_OUT:
                # Expected if device is idle, continue polling
                time.sleep(0.01)
                continue
            else:
                # Actual read error
                print(f"Error reading response: {status}")
                response = None # Indicate read error
                break

        # Restore default timeouts after operation
        self._set_timeouts(DEFAULT_READ_TIMEOUT_MS, DEFAULT_WRITE_TIMEOUT_MS)

        if response is None:
             if self.debug: print("DEBUG RX: Read Error")
             return None

        timed_out = (time.time() - read_start_time) * 1000 >= timeout_ms
        if timed_out and not response:
            if self.debug: print("DEBUG RX: Read Timeout (No data)")
            return None # Indicate timeout with no data
        elif timed_out and response:
             # LF wasn't received before overall timeout
             if self.debug: print(f"DEBUG RX (Timeout before LF): '{response.strip()}'")
             return response.strip() # Return potentially partial response

        if self.debug: print(f"DEBUG RX: '{response.strip()}'")
        return response.strip()

    def query_command(self, command, query_timeout_ms=RESPONSE_READ_TIMEOUT_MS):
        """Send a query command and read the response."""
        if not self._is_open: return None
        # Remove the strict check for ending with '?' as some valid queries might not (e.g., STEPRSLT?,1)
        # if not command.endswith('?'):
        #     print(f"Warning: Query command '{command}' does not end with '?'")

        if self.send_command(command):
            time.sleep(0.1) # Allow device time to process
            return self.read_response(timeout_ms=query_timeout_ms)
        else:
            print(f"Failed to send query command: {command}")
            return None

    @property
    def is_open(self):
        return self._is_open

    def __enter__(self):
        """Context manager entry: attempts to open the device."""
        if not self.find_device() > 0:
            raise V7xDeviceError("No V7X devices found.")
        if not self.open():
             raise V7xDeviceError("Failed to open V7X device.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: ensures the device is closed."""
        self.close() 
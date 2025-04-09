import ctypes

# Device Identification
VID = 4292 # Default Vitrek VID
PID = 34869 # Default Vitrek V7X PID

# --- IMPORTANT: Update this path to the actual location of your DLL file ---
# Example path, CHANGE THIS if your DLL is elsewhere
DLL_PATH = r"C:\Coding\hipot\SLABHIDtoUART.dll"

# Define Basic CTypes used by the DLL
DWORD = ctypes.c_ulong
WORD = ctypes.c_ushort
BYTE = ctypes.c_ubyte
BOOL = ctypes.c_int
HID_UART_STATUS = ctypes.c_int # Return type for many functions
HID_UART_DEVICE = ctypes.c_void_p # Opaque pointer for device handle

# HID_UART Status Codes (from SLABHIDtoUART.h or common usage)
HID_UART_SUCCESS = 0x00
HID_UART_DEVICE_NOT_FOUND = 0x01
HID_UART_INVALID_HANDLE = 0x02
HID_UART_INVALID_DEVICE_OBJECT = 0x03
HID_UART_INVALID_PARAMETER = 0x04
HID_UART_INVALID_REQUEST_LENGTH = 0x05

HID_UART_READ_ERROR = 0x10
HID_UART_WRITE_ERROR = 0x11
HID_UART_READ_TIMED_OUT = 0x12
HID_UART_WRITE_TIMED_OUT = 0x13
HID_UART_DEVICE_IO_FAILED = 0x14
HID_UART_DEVICE_ACCESS_ERROR = 0x15
HID_UART_DEVICE_NOT_SUPPORTED = 0x16

# UART Configuration Constants
# Data Bits
HID_UART_FIVE_DATA_BITS = 0x00
HID_UART_SIX_DATA_BITS = 0x01
HID_UART_SEVEN_DATA_BITS = 0x02
HID_UART_EIGHT_DATA_BITS = 0x03

# Parity
HID_UART_NO_PARITY = 0x00
HID_UART_ODD_PARITY = 0x01
HID_UART_EVEN_PARITY = 0x02
HID_UART_MARK_PARITY = 0x03
HID_UART_SPACE_PARITY = 0x04

# Stop Bits
HID_UART_SHORT_STOP_BIT = 0x00 # 1 stop bit
HID_UART_LONG_STOP_BIT = 0x01 # 1.5 or 2 stop bits (check documentation)

# Flow Control
HID_UART_NO_FLOW_CONTROL = 0x00
HID_UART_RTS_CTS_FLOW_CONTROL = 0x01 # Hardware flow control
# Other flow control options might exist

# String Types for GetString (if used)
HID_UART_GET_VID_STR = 1
HID_UART_GET_PID_STR = 2
HID_UART_GET_PATH_STR = 3
HID_UART_GET_SERIAL_STR = 4
HID_UART_GET_MANUFACTURER_STR = 5
HID_UART_GET_PRODUCT_STR = 6

# Default Communication Parameters
DEFAULT_BAUD_RATE = 115200
DEFAULT_READ_TIMEOUT_MS = 100 # Short timeout for polling reads
DEFAULT_WRITE_TIMEOUT_MS = 1000
# Timeout for blocking reads (e.g., waiting for a response)
RESPONSE_READ_TIMEOUT_MS = 3000

# Test Type Definitions (used in GUI/Sequencer)
TEST_TYPES = {
    "ACW": "AC Withstand Voltage Test",
    "DCW": "DC Withstand Voltage Test",
    "IR": "Insulation Resistance Test",
    "CONT": "Continuity Test",
    "GND": "Ground Bond Test"
}

# SCPI Status Code Flags (Bitmask for RSLT? and STEPRSLT? status_code)
# Source: V7x Manual
STATUS_FLAGS = {
    1: "V7X Internal Fault",
    2: "Over Voltage Output",
    4: "Line Too Low",
    8: "DUT Breakdown Detected",
    16: "HOLD Step Timeout",
    32: "User Aborted Sequence",
    64: "GB Over-Compliance",
    128: "Arc Detected",
    256: "Measurement < Min Limit",
    512: "Measurement > Max Limit",
    1024: "IR Not Steady/Decreasing", # Specific IR termination mode
    2048: "Interlock Failure",
    4096: "Switch Matrix Error",
    8192: "V7X Overheated",
    16384: "Unstable Load/Control Error", # DUT voltage/current unstable
    32768: "GB Wiring Error",
    65536: "Voltage Error" # Unstable drive or varying leakage/resistance
}

# SCPI Termination State Codes (First field from STEPRSLT?)
TERMINATION_STATES = {
    "0": "Not Executed",
    "1": "Terminated Before Start",
    "2": "Terminated during Ramp",
    "3": "Terminated during Dwell",
    "4": "Completed Normally", # Assumed based on typical usage
    # Add other codes if known from documentation
    "?": "Unknown/In Process" # Placeholder if queried while running
} 
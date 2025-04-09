import ctypes
import sys
import time
import re # Import regular expressions for parsing

# Configuration
VID = 4292 # Default Vitrek VID
PID = 34869 # Default Vitrek V7X PID
# --- IMPORTANT: Update this path to the actual location of your DLL file ---
dll_path = r"C:\Coding\hipot\SLABHIDtoUART.dll" # Example path, CHANGE THIS

# Define Types based on C types for ctypes
DWORD = ctypes.c_ulong
WORD = ctypes.c_ushort
BYTE = ctypes.c_ubyte
BOOL = ctypes.c_int # Note: C BOOL is often typedef'd as int
HID_UART_STATUS = ctypes.c_int
HID_UART_DEVICE = ctypes.c_void_p # void* equivalent

# Constants from SLABHIDtoUART.h (or typical values)
HID_UART_SUCCESS = 0x00
HID_UART_DEVICE_NOT_FOUND = 0x01
HID_UART_INVALID_HANDLE = 0x02
# ... (add other status codes as needed) ...
HID_UART_READ_TIMED_OUT = 0x12
HID_UART_WRITE_TIMED_OUT = 0x13
# UART Config Constants
HID_UART_EIGHT_DATA_BITS = 0x03
HID_UART_NO_PARITY = 0x00
HID_UART_SHORT_STOP_BIT = 0x00 # 1 stop bit
HID_UART_LONG_STOP_BIT = 0x01 # 2 stop bits
HID_UART_RTS_CTS_FLOW_CONTROL = 0x01 # Hardware flow control
HID_UART_NO_FLOW_CONTROL = 0x00

# --- Load DLL ---
try:
    hid_uart_dll = ctypes.WinDLL(dll_path)
except OSError as e:
    print(f"Error loading DLL from path: {dll_path}")
    print(f"OSError: {e}")
    print("Please ensure the DLL path is correct and the DLL is compatible (32/64-bit).")
    sys.exit(1) # Exit if DLL can't be loaded

# --- Define Function Signatures ---
# Define argtypes and restype for each function used from the DLL
# This helps ctypes with type checking and marshalling
try:
    hid_uart_dll.HidUart_GetNumDevices.argtypes = [ctypes.POINTER(DWORD), WORD, WORD]
    hid_uart_dll.HidUart_GetNumDevices.restype = HID_UART_STATUS

    hid_uart_dll.HidUart_Open.argtypes = [ctypes.POINTER(HID_UART_DEVICE), DWORD, WORD, WORD]
    hid_uart_dll.HidUart_Open.restype = HID_UART_STATUS

    hid_uart_dll.HidUart_SetUartConfig.argtypes = [HID_UART_DEVICE, DWORD, BYTE, BYTE, BYTE, BYTE]
    hid_uart_dll.HidUart_SetUartConfig.restype = HID_UART_STATUS

    hid_uart_dll.HidUart_SetTimeouts.argtypes = [HID_UART_DEVICE, DWORD, DWORD]
    hid_uart_dll.HidUart_SetTimeouts.restype = HID_UART_STATUS

    hid_uart_dll.HidUart_Write.argtypes = [HID_UART_DEVICE, ctypes.POINTER(BYTE), DWORD, ctypes.POINTER(DWORD)]
    hid_uart_dll.HidUart_Write.restype = HID_UART_STATUS

    hid_uart_dll.HidUart_Read.argtypes = [HID_UART_DEVICE, ctypes.POINTER(BYTE), DWORD, ctypes.POINTER(DWORD)]
    hid_uart_dll.HidUart_Read.restype = HID_UART_STATUS

    hid_uart_dll.HidUart_Close.argtypes = [HID_UART_DEVICE]
    hid_uart_dll.HidUart_Close.restype = HID_UART_STATUS

    hid_uart_dll.HidUart_FlushBuffers.argtypes = [HID_UART_DEVICE, BOOL, BOOL]
    hid_uart_dll.HidUart_FlushBuffers.restype = HID_UART_STATUS

    # Check if GetLibraryVersion exists (might not be in all DLL versions)
    try:
        hid_uart_dll.HidUart_GetLibraryVersion.argtypes = [ctypes.POINTER(BYTE), ctypes.POINTER(BYTE), ctypes.POINTER(BOOL)]
        hid_uart_dll.HidUart_GetLibraryVersion.restype = HID_UART_STATUS
        has_version_api = True
    except AttributeError:
        has_version_api = False

except AttributeError as e:
    print(f"Error accessing function in DLL: {e}")
    print("The DLL might be missing expected functions or is corrupted.")
    sys.exit(1)

# --- Helper Functions ---

def get_library_version():
    """Get the DLL library version if available"""
    if not has_version_api:
        return "Unknown (API not available)"

    major = BYTE(0)
    minor = BYTE(0)
    release = BOOL(0)
    status = hid_uart_dll.HidUart_GetLibraryVersion(ctypes.byref(major), ctypes.byref(minor), ctypes.byref(release))

    if status == HID_UART_SUCCESS:
        return f"{major.value}.{minor.value} (Release: {bool(release.value)})"
    else:
        return f"Error getting version: {status}"

def send_command(device_handle, command, debug=False):
    """Send a command string to the device, adding CR termination."""
    if not command.endswith('\r'):
        command += '\r' # V7X uses Carriage Return termination

    cmd_bytes = command.encode('ascii') # Convert string to ASCII bytes
    # Create a ctypes byte buffer from the Python bytes object
    cmd_buffer = (BYTE * len(cmd_bytes)).from_buffer_copy(cmd_bytes)
    bytes_written = DWORD(0)

    if debug: print(f"DEBUG TX: {command.strip()}") # Show command being sent

    status = hid_uart_dll.HidUart_Write(
        device_handle,
        cmd_buffer,
        DWORD(len(cmd_bytes)),
        ctypes.byref(bytes_written)
    )

    if status != HID_UART_SUCCESS:
        print(f"Error sending command: {status}")
        return False
    if bytes_written.value != len(cmd_bytes):
        print(f"Warning: Bytes written ({bytes_written.value}) != Command length ({len(cmd_bytes)})")
        # Continue anyway, might be partial write scenario

    return True

def read_response(device_handle, timeout_ms=3000, debug=False):
    """
    Read response from the device until LF or timeout.
    Handles potential timeouts and errors during read.
    """
    response = ""
    read_buffer = (BYTE * 1)() # Buffer to read one byte at a time
    read_start_time = time.time()

    # Configure read timeout for this operation specifically
    # Using a short timeout per read attempt, but loop until overall timeout_ms
    # This prevents blocking indefinitely if device sends data slowly.
    # Set a reasonable per-read timeout (e.g., 50ms)
    hid_uart_dll.HidUart_SetTimeouts(device_handle, DWORD(50), DWORD(1000)) # 50ms read, 1s write

    while (time.time() - read_start_time) * 1000 < timeout_ms:
        bytes_read = DWORD(0)
        status = hid_uart_dll.HidUart_Read(device_handle, read_buffer, DWORD(1), ctypes.byref(bytes_read))

        if status == HID_UART_SUCCESS:
            if bytes_read.value == 1:
                char_code = read_buffer[0]
                # Check for Line Feed (LF) which terminates V7X responses
                if char_code == ord(b'\n'):
                    break # End of response found
                # Append character, ignoring Carriage Return (CR)
                if char_code != ord(b'\r'):
                    response += chr(char_code)
                # Reset timer slightly on successful read to allow for inter-character gaps
                read_start_time = time.time()
            else:
                # No data read in this attempt, yield briefly
                time.sleep(0.01)
        elif status == HID_UART_READ_TIMED_OUT:
            # This is expected if device is idle, continue loop until overall timeout
            time.sleep(0.01) # Small delay before next poll
            continue
        else:
            # An actual error occurred during read
            print(f"Error reading response: {status}")
            return None # Indicate read error

    # Reset timeouts to default (e.g., 100ms read, 1000ms write) after operation
    hid_uart_dll.HidUart_SetTimeouts(device_handle, DWORD(100), DWORD(1000))

    if (time.time() - read_start_time) * 1000 >= timeout_ms and not response:
        if debug: print("DEBUG RX: Read timeout (no data received)")
        return None # Indicate overall timeout with no data
    elif (time.time() - read_start_time) * 1000 >= timeout_ms and response:
         if debug: print(f"DEBUG RX (Timeout before LF): '{response.strip()}'")
         return response.strip() # Return potentially partial response on timeout

    if debug: print(f"DEBUG RX: '{response.strip()}'")
    return response.strip() # Return complete response

def query_command(device_handle, command, debug=False):
    """Send a query command (ending in '?') and read the response."""
    if not command.endswith('?'):
        print(f"Warning: Command '{command}' sent to query_command does not end with '?'")
        # Decide if you want to proceed or return an error
        # Proceeding for flexibility, but it might not return useful data

    if send_command(device_handle, command, debug):
        # Add a small delay - V7X might need time to process command before responding
        time.sleep(0.1) # Adjust as needed, 0.1s is often sufficient
        response = read_response(device_handle, debug=debug)
        return response # Can be None if read failed or timed out
    else:
        print(f"Failed to send query command: {command}")
        return None # Indicate send failure

def parse_current_input(input_str, default_unit='A'):
    """
    Parses a current string (e.g., "10mA", "50uA", "0.01A", "15")
    and returns the value in Amps as a string.
    Returns None if parsing fails.
    """
    if not input_str:
        return "" # Return empty string if input is blank (often allowed for limits)

    input_str = input_str.strip()
    # Regular expression to capture value and optional unit (mA, uA, A)
    # Allows for floating point numbers, scientific notation (e.g., 1.5e-3)
    match = re.match(r"^(-?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([mu]?[aA]?)?$", input_str, re.IGNORECASE)

    if not match:
        print(f"Error: Invalid current format '{input_str}'. Use numbers like 10mA, 50uA, 0.01A, or 15.")
        return None # Indicate parsing error

    value_str, unit = match.groups()
    try:
        value = float(value_str)
    except ValueError:
         print(f"Error: Could not convert value '{value_str}' to a number.")
         return None # Indicate conversion error

    unit = unit.lower() if unit else default_unit.lower() # Default to Amps if no unit

    if unit == 'ma':
        value /= 1000.0
    elif unit == 'ua':
        value /= 1000000.0
    elif unit == 'a' or not unit: # Handle 'A' or no unit as Amps
        pass # Value is already in Amps
    else:
         print(f"Error: Unknown current unit '{unit}' in '{input_str}'. Use mA, uA, or A.")
         return None # Indicate parsing error

    # Return as string, formatted to avoid excessive precision issues for SCPI
    # Using general format 'g' which avoids trailing zeros and switches to scientific if needed
    return f"{value:g}"

def setup_test_sequence(device_handle, debug=False):
    """Interactive configuration of a test sequence with easier current input"""
    print("\nTest Sequence Setup")
    print("===================")

    # First clear any existing sequence
    if query_command(device_handle, "*ERR?", debug) != "0":
        print("Clearing errors...")
        send_command(device_handle, "*CLS", debug)

    print("Clearing previous test sequence...")
    if not send_command(device_handle, "NOSEQ", debug):
        print("Failed to clear test sequence (NOSEQ command failed)")
        # Query error again to see why NOSEQ might have failed
        err = query_command(device_handle, "*ERR?", debug)
        print(f"Error status after NOSEQ attempt: {err}")
        return False # Cannot proceed if clearing fails

    # Short delay after NOSEQ before adding steps
    time.sleep(0.2)

    step_count = 0
    continue_adding = True
    steps_successfully_added = 0 # Track actual successful steps

    while continue_adding:
        current_step_number = steps_successfully_added + 1 # The step number we are trying to add
        print(f"\n--- Configuring Test Step {current_step_number} ---")

        # Get test type
        print("\nAvailable test types:")
        test_types = [
            ("ACW", "AC Withstand Voltage Test"),
            ("DCW", "DC Withstand Voltage Test"),
            ("IR", "Insulation Resistance Test"),
            ("CONT", "Continuity Test"),
            ("GND", "Ground Bond Test")
        ]

        for i, (code, desc) in enumerate(test_types, 1):
            print(f"{i}. {code:<4} - {desc}")

        try:
            choice_input = input(f"\nSelect test type for Step {current_step_number} [1-{len(test_types)}]: ")
            if not choice_input:
                 print("No selection made.")
                 continue # Ask again

            choice = int(choice_input)
            if choice < 1 or choice > len(test_types):
                print("Invalid selection number.")
                continue # Go back to test type selection

            test_type = test_types[choice-1][0]
            print(f"Selected: {test_type}")

            params = []
            valid_params = True # Flag to track if all params for *this step* are valid

            # --- Parameter Input Logic ---
            if test_type == "ACW":
                voltage = input("Test voltage [V, 50-5000]: ") or "1000"
                ramp_time = input("Ramp time [s, 0.1-999]: ") or "1.0"
                dwell_time = input("Dwell time [s, 0.2-999]: ") or "2.0"
                min_limit_input = input("Minimum current limit [e.g., 10uA, 1mA, blank for none]: ")
                min_limit = parse_current_input(min_limit_input)
                if min_limit is None: valid_params = False
                max_limit_input = input(f"Maximum current limit [e.g., 20mA, 0.01A]: ") or "5mA"
                max_limit = parse_current_input(max_limit_input)
                if max_limit is None: valid_params = False
                gnd = input("Ground check [Y/N]: ").upper()
                ground = "GND" if gnd == "Y" else ""
                if valid_params:
                    params.extend([voltage, ramp_time, dwell_time, min_limit, max_limit])
                    if ground: params.append(ground)

            elif test_type == "DCW":
                voltage = input("Test voltage [V, 50-6000]: ") or "1000"
                ramp_time = input("Ramp time [s, 0.1-999]: ") or "1.0"
                dwell_time = input("Dwell time [s, 0.2-999]: ") or "2.0"
                min_limit_input = input("Minimum current limit [e.g., 1uA, blank for none]: ")
                min_limit = parse_current_input(min_limit_input)
                if min_limit is None: valid_params = False
                max_limit_input = input("Maximum current limit [e.g., 5mA, 500uA]: ") or "5mA"
                max_limit = parse_current_input(max_limit_input)
                if max_limit is None: valid_params = False
                gnd = input("Ground check [Y/N]: ").upper()
                ground = "GND" if gnd == "Y" else ""
                if valid_params:
                    params.extend([voltage, ramp_time, dwell_time, min_limit, max_limit])
                    if ground: params.append(ground)

            elif test_type == "IR":
                 # Consider adding parsing for resistance (kΩ, MΩ, GΩ) here if desired
                 voltage = input("Test voltage [V, 50-6000]: ") or "500"
                 ramp_time = input("Ramp time [s, 0.1-999]: ") or "1.0"
                 dwell_time = input("Dwell time [s, 0.2-999]: ") or "2.0"
                 min_limit = input("Minimum resistance [\u03A9, e.g., 1M, 500k, blank for none]: ") # Example prompt update
                 # min_limit_parsed = parse_resistance_input(min_limit) # Call hypothetical parser
                 max_limit = input("Maximum resistance [\u03A9, e.g., 10G, blank for none]: ")
                 # max_limit_parsed = parse_resistance_input(max_limit)
                 # if min_limit_parsed is None or max_limit_parsed is None: valid_params = False
                 if valid_params: # Replace with parsed values if implemented
                     params.extend([voltage, ramp_time, dwell_time, min_limit, max_limit])

            elif test_type == "CONT":
                 # Continuity test current is often simpler, might not need mA/uA parsing
                 current = input("Test current [A, 0.01-30]: ") or "0.1"
                 min_limit = input("Minimum resistance [\u03A9, blank for none]: ")
                 max_limit = input("Maximum resistance [\u03A9, e.g., 0.5]: ") or "0.1" # Sensible default?
                 dwell_time = input("Dwell time [s, 0.2-999]: ") or "1.0" # Shorter default?
                 params.extend([current, min_limit, max_limit, dwell_time])

            elif test_type == "GND":
                 current = input("Test current [A, 1-30]: ") or "10"
                 max_limit = input("Maximum resistance [\u03A9, 0.001-1]: ") or "0.1"
                 dwell_time = input("Dwell time [s, 0.2-999]: ") or "2.0"
                 freq = input("Frequency [Hz, 50/60]: ") or "60"
                 params.extend([current, max_limit, dwell_time, freq])

            # --- End Parameter Input Logic ---

            if not valid_params:
                 print("Invalid parameter entered during setup for this step. Please try configuring the step again.")
                 # Don't increment step count, loop will restart for the same step number
                 continue

            # --- Build and send ADD command ---
            add_command = f"ADD,{test_type}"
            for param in params:
                add_command += ","
                add_command += str(param) # Handles blank "" correctly

            print(f"\nSending command: {add_command}")

            step_added_successfully = False
            if send_command(device_handle, add_command, debug):
                # Wait briefly for command processing and error status update
                time.sleep(0.2)
                # Check for errors *after* sending command
                err = query_command(device_handle, "*ERR?", debug)
                if err == "0":
                    print(f"Step {current_step_number} added successfully!")
                    steps_successfully_added += 1 # Increment successful steps counter
                    step_added_successfully = True
                else:
                    print(f"Error setting up Step {current_step_number}: {err} (Check parameter ranges/formats for '{test_type}')")
                    # Device rejected the step, do not increment steps_successfully_added
            else:
                print(f"Failed to send ADD command for Step {current_step_number}.")
                # Error sending command itself

            # --- Ask to add another step ---
            if step_added_successfully:
                another = input("\nAdd another test step? [Y/N]: ").upper()
                if another != "Y":
                    continue_adding = False
            else:
                # If the step failed (parsing, sending, or device error), ask user how to proceed
                retry = input("Failed to add this step. Retry configuring this step? [Y/N]: ").upper()
                if retry != 'Y':
                    continue_adding = False # Stop adding steps if user doesn't want to retry


        except ValueError:
            print("Invalid input (expected a number for selection). Please try again.")
            # Don't change continue_adding, just loop again for the same step number
        except KeyboardInterrupt:
            print("\nSetup cancelled by user.")
            continue_adding = False

    # --- Final Report ---
    print("\nTest sequence configuration finished.")
    # Query the actual number of steps from the device as final confirmation
    actual_steps = query_command(device_handle, "STEP?", debug)
    if actual_steps is not None:
         print(f"Device reports {actual_steps} step(s) configured.")
         if int(actual_steps) != steps_successfully_added:
              print(f"Warning: Mismatch between expected steps ({steps_successfully_added}) and device report ({actual_steps}).")
    else:
         print("Could not verify number of steps configured on device.")

    return steps_successfully_added > 0 # Return True if at least one step was likely added


def run_test_sequence(device_handle, debug=False):
    """Run the configured test sequence and display results"""
    print("\nRunning test sequence...")

    # Get the number of steps currently configured
    num_steps_str = query_command(device_handle, "STEP?", debug)
    try:
        num_steps = int(num_steps_str)
        if num_steps <= 0:
             print("No test sequence configured or device reported zero steps. Please set up a test sequence first.")
             return False
    except (TypeError, ValueError):
         print(f"Error: Could not determine number of steps (Received: '{num_steps_str}'). Cannot run test.")
         return False

    print(f"Attempting to run test sequence with {num_steps} step(s).")
    time.sleep(0.1) # Small pause before RUN

    # Clear any previous errors or results before starting
    send_command(device_handle, "*CLS", debug)
    time.sleep(0.1)

    # Start the test
    if not send_command(device_handle, "RUN", debug):
        print("Failed to send RUN command.")
        err = query_command(device_handle, "*ERR?", debug)
        print(f"Error status after failed RUN attempt: {err}")
        return False

    # --- Poll for completion ---
    print("Test running (or attempting to start)... Waiting for completion...")
    test_start_time = time.time()
    # Set a maximum wait time for the entire test sequence (e.g., 1 hour)
    # Adjust this based on expected longest test sequence duration
    max_test_wait_sec = 3600

    while (time.time() - test_start_time) < max_test_wait_sec :
        time.sleep(0.5) # Polling interval
        run_status = query_command(device_handle, "RUN?", debug)

        if run_status == "0":
            print("Test sequence completed.")
            break # Exit polling loop
        elif run_status == "1":
            # Still running, continue polling
            # Optional: Print elapsed time or current step if needed
            # current_step = query_command(device_handle, "CURRSTEP?", debug) # Example command
            # print(f"Elapsed: {time.time() - test_start_time:.1f}s, Step: {current_step}")
            continue
        elif run_status is None:
             print("Warning: Failed to get RUN? status. Continuing to poll...")
             # Could indicate communication issue, keep trying for a bit
        else:
            # Unexpected status (e.g., error code?)
            print(f"Warning: Unexpected RUN? status: {run_status}. Checking error...")
            err = query_command(device_handle, "*ERR?", debug)
            print(f"Error status: {err}")
            # Decide whether to abort based on the error or unexpected status
            print("Aborting test due to unexpected status.")
            send_command(device_handle, "ABORT", debug)
            return False # Test did not complete normally

    else: # Reached if the while loop exits due to timeout
         print(f"Error: Test sequence did not complete within the maximum wait time ({max_test_wait_sec} seconds).")
         print("Aborting test.")
         send_command(device_handle, "ABORT", debug)
         return False

    # --- Get and Display Results ---
    time.sleep(0.1) # Allow results to stabilize
    overall_result = query_command(device_handle, "RSLT?", debug)

    if overall_result == "0":
        print("\nOVERALL RESULT: PASS")
    elif overall_result is not None:
         print(f"\nOVERALL RESULT: FAIL (Status Code: {overall_result})")
         # Could add lookup for common fail codes here
    else:
        print("\nOVERALL RESULT: Unknown (Failed to query RSLT?)")


    print("\n--- Detailed Step Results ---")
    for step in range(1, num_steps + 1):
        # Use STEPRSLT? command (check manual for exact command and parameters)
        # Format is often STEPRSLT?,<step_number>
        step_result_str = query_command(device_handle, f"STEPRSLT?,{step}", debug)

        print(f"\nStep {step}:")
        if step_result_str:
            print(f"  Raw Data: '{step_result_str}'")
            # Attempt to parse the comma-separated result string
            try:
                fields = step_result_str.split(',')
                # Expected fields based on V7X manual (adjust indices if necessary)
                # Example: TermState, ElapsedTime, StatusCode, Level, Limit, Measurement, [MaxArc]
                if len(fields) >= 6:
                    term_state = fields[0]
                    elapsed_time = fields[1]
                    status_code = fields[2]
                    level = fields[3] # Voltage or Current Level applied
                    limit = fields[4] # The limit that was compared against
                    measurement = fields[5] # The measured value (Current, Resistance)

                    print(f"  Termination State : {term_state}") # e.g., PASS, FAILHI, FAILLO, ABORT
                    print(f"  Elapsed Time      : {elapsed_time} s")
                    print(f"  Status Code       : {status_code} {'(Pass)' if status_code == '0' else '(Fail/Other)'}")
                    print(f"  Test Level        : {level}") # Units depend on test type
                    print(f"  Limit             : {limit}") # Units depend on test type
                    print(f"  Measurement       : {measurement}") # Units depend on test type

                    # Optional fields like Max Arc Current
                    if len(fields) > 6:
                        arc = fields[6]
                        print(f"  Max Arc           : {arc}") # Usually in Amps for ACW/DCW

                else:
                    print("  Warning: Could not parse expected number of fields from result.")
            except Exception as e:
                print(f"  Error parsing results for step {step}: {e}")
        else:
            print(f"  Could not retrieve results for step {step}.")

    return True # Indicate test run attempt finished (pass or fail)


def execute_command(command, is_query=False, debug=False):
    """Connects, executes a single command/query or special function, and disconnects."""
    print("-" * 20) # Separator for clarity

    # Find devices
    num_devices = DWORD(0)
    status = hid_uart_dll.HidUart_GetNumDevices(ctypes.byref(num_devices), WORD(VID), WORD(PID))

    if status != HID_UART_SUCCESS:
        print(f"Error checking for devices: {status}")
        return
    if num_devices.value == 0:
        print(f"No devices found with VID={VID}, PID={PID}")
        print("Check connection and VID/PID configuration.")
        return

    print(f"Found {num_devices.value} device(s). Attempting to open device 0...")

    # Open device (using index 0)
    device_handle = HID_UART_DEVICE(None)
    status = hid_uart_dll.HidUart_Open(ctypes.byref(device_handle), DWORD(0), WORD(VID), WORD(PID))

    if status != HID_UART_SUCCESS or not device_handle.value:
        print(f"Error opening device 0: {status}")
        # If multiple devices, could try opening next index
        return

    print("Device opened successfully.")

    try:
        # --- Configure UART ---
        # Baud rate, data bits, parity, stop bits, flow control
        # Match these to the V7X RS232 settings if applicable,
        # although for HID-UART bridge, these might configure the virtual COM port.
        # 115200 is often used for Vitrek remote control.
        baud_rate = DWORD(115200)
        data_bits = BYTE(HID_UART_EIGHT_DATA_BITS)
        parity = BYTE(HID_UART_NO_PARITY)
        stop_bits = BYTE(HID_UART_SHORT_STOP_BIT)
        flow_control = BYTE(HID_UART_RTS_CTS_FLOW_CONTROL) # Or HID_UART_NO_FLOW_CONTROL

        status = hid_uart_dll.HidUart_SetUartConfig(
            device_handle, baud_rate, data_bits, parity, stop_bits, flow_control
        )
        if status != HID_UART_SUCCESS:
            # This might not be critical for all operations if defaults work
            print(f"Warning: Failed to configure UART: {status}")

        # --- Configure Timeouts ---
        # Read timeout (ms), Write timeout (ms)
        read_timeout_ms = DWORD(100) # Default read timeout
        write_timeout_ms = DWORD(1000) # Default write timeout
        status = hid_uart_dll.HidUart_SetTimeouts(device_handle, read_timeout_ms, write_timeout_ms)
        if status != HID_UART_SUCCESS:
             print(f"Warning: Failed to set timeouts: {status}")

        # --- Flush Buffers --- (Good practice before starting communication)
        status = hid_uart_dll.HidUart_FlushBuffers(device_handle, BOOL(True), BOOL(True)) # Flush TX and RX
        if status != HID_UART_SUCCESS:
             print(f"Warning: Failed to flush buffers: {status}")
        time.sleep(0.1) # Allow time for flush

        # --- Handle Special Internal Commands ---
        if command == "__SETUP_TEST__":
            setup_test_sequence(device_handle, debug)
        elif command == "__RUN_TEST__":
            run_test_sequence(device_handle, debug)
        # --- Standard SCPI Command/Query Handling ---
        else:
            print(f"Sending command: '{command}'")
            if is_query:
                response = query_command(device_handle, command, debug)
                if response is not None:
                    print(f"Response: '{response}'")
                else:
                    print("No response received or error occurred.")
            else: # It's an action command
                if send_command(device_handle, command, debug):
                    print("Command sent successfully.")
                    # Optional: Short delay and check error status
                    time.sleep(0.2)
                    err_status = query_command(device_handle, "*ERR?", debug)
                    if err_status != "0":
                         print(f"Device reported error after command: {err_status}")
                else:
                    print("Failed to send command.")

        # Wait for user to see result only if running interactively (not via command line arg)
        if len(sys.argv) <= 1 and command not in ["__SETUP_TEST__", "__RUN_TEST__"]:
             # Don't wait after complex functions like setup/run which have internal waits/prompts
             input("\nPress Enter to continue...")

    except Exception as e:
         print(f"\nAn unexpected error occurred during device communication: {e}")
         # Add more specific error handling if needed
    finally:
        # --- Close Device --- Ensure device is closed even if errors occurred
        if device_handle and device_handle.value:
            status = hid_uart_dll.HidUart_Close(device_handle)
            if status == HID_UART_SUCCESS:
                print("Device closed.")
            else:
                print(f"Error closing device: {status}")
        print("-" * 20) # Separator


def main():
    """Main function to run the interactive menu or execute a single command."""
    print(f"SLABHIDtoUART Library Version: {get_library_version()}")

    # Predefined commands list with descriptions for the menu
    command_list = [
        ("*IDN?", "Get device identification"),
        ("*RST", "Reset device"),
        ("*ERR?", "Check for errors"),
        ("*CLS", "Clear status (error queue)"),
        ("*TST?", "Run self-test"),
        ("RUN?", "Check if sequence is running (1=Yes, 0=No)"),
        ("RSLT?", "Get overall result status (0=Pass)"),
        ("STEP?", "Get number of configured steps"),
        ("NOSEQ", "Clear test sequence"),
        ("RUN", "Start test sequence"),
        ("CONT", "Continue paused test"), # Check if V7X uses this exact command
        ("ABORT", "Abort test"),
        ("MEASRSLT?,OHMS", "Get last ohms measurement (if applicable)"), # Check command
        ("MEASRSLT?,AC", "Get last AC measurement (if applicable)"), # Check command
        ("MEASRSLT?,DC", "Get last DC measurement (if applicable)"), # Check command
        ("MEASRSLT?,IR", "Get last IR measurement (if applicable)"), # Check command
    ]

    debug_mode = False # Initialize debug mode

    # --- Command Line Argument Handling ---
    if len(sys.argv) > 1:
        command = sys.argv[1]
        is_query = command.endswith('?')
        # Execute directly, assume debug for command line calls
        print(f"Executing command from argument: {command}")
        execute_command(command, is_query, debug=True)
        return # Exit after executing command line argument

    # --- Interactive Menu ---
    while True:
        try:
            print("\nV7X HID Command Interface")
            print("=========================")
            print(f"Current VID: {VID}, PID: {PID}")
            print("Available commands:")

            for i, (cmd, desc) in enumerate(command_list, 1):
                print(f"{i}. {cmd:<18} - {desc}")

            print("\nTest Functions:")
            print("S. Setup test sequence")
            print("R. Run configured test")

            print("\nOptions:")
            print("C. Custom command")
            print(f"D. Debug mode ({'ON' if debug_mode else 'OFF'})")
            print("Q. Quit")

            choice = input("\nSelect option: ").strip()

            if not choice: continue # Handle empty input

            if choice.upper() == 'Q':
                print("Exiting program.")
                break
            elif choice.upper() == 'D':
                debug_mode = not debug_mode
                print(f"Debug mode {'enabled' if debug_mode else 'disabled'}")
                continue # Show menu again
            elif choice.upper() == 'C':
                custom_cmd = input("Enter custom command: ").strip()
                if custom_cmd:
                    is_query = custom_cmd.endswith('?')
                    execute_command(custom_cmd, is_query, debug=debug_mode)
                else:
                    print("No command entered.")
            elif choice.upper() == 'S':
                execute_command("__SETUP_TEST__", False, debug=debug_mode)
            elif choice.upper() == 'R':
                execute_command("__RUN_TEST__", False, debug=debug_mode)
            else:
                # Handle numbered command selection
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(command_list):
                        cmd, _ = command_list[idx]
                        is_query = cmd.endswith('?')
                        execute_command(cmd, is_query, debug=debug_mode)
                    else:
                        print("Invalid selection number. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter a number or option letter.")

        except KeyboardInterrupt:
            print("\nOperation interrupted by user. Exiting.")
            break
        except Exception as e:
            # Catch unexpected errors during the main loop
            print(f"\nAn unexpected error occurred in the main loop: {e}")
            # Consider adding more robust error handling or logging here
            continue # Attempt to continue the loop

if __name__ == "__main__":
    main()
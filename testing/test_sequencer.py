import time
import json # Import json for handling JSONB
from device.v7x_device import V7xDevice
from utils.parsing import parse_current_input
# Import TEST_TYPES if needed directly, or pass from GUI
from utils.constants import TEST_TYPES
# Import supabase client utility
from utils.supabase_client import get_supabase_client

class TestSequencer:
    """Manages building and running test sequences on the V7x device."""

    def __init__(self, device: V7xDevice):
        """Initialize the test sequencer for the given device."""
        if not isinstance(device, V7xDevice):
            raise TypeError("TestSequencer requires a V7xDevice instance.")
        self.device = device
        self.sequence = [] # List to store configured steps (e.g., dictionaries)
        self.current_sequence_id = None # ID of the currently loaded/saved sequence
        self.current_sequence_name = None # Name of the currently loaded/saved sequence
        self.current_sequence_description = None # Description of the currently loaded/saved sequence
        self.debug = device.debug # Inherit debug state from device
        self.supabase_client = get_supabase_client()

    def clear_sequence_on_device(self):
        """Sends NOSEQ to clear the hardware sequence."""
        if not self.device.is_open:
            print("Error: Device not open to clear sequence.")
            return False

        # Clear errors first
        err_status = self.device.query_command("*ERR?")
        if err_status and err_status != "0":
            print("Clearing existing errors before NOSEQ...")
            self.device.send_command("*CLS")
            time.sleep(0.1)

        print("Clearing device test sequence (NOSEQ)...")
        if not self.device.send_command("NOSEQ"):
            print("Failed to send NOSEQ command.")
            return False

        # Verify error status after NOSEQ
        time.sleep(0.2) # Allow time for command processing
        err_status = self.device.query_command("*ERR?")
        if err_status is None:
            print("Warning: Could not verify error status after NOSEQ.")
            return False # Uncertain state
        elif err_status != "0":
            print(f"Error after NOSEQ: {err_status}")
            return False

        print("Device sequence cleared.")
        self.sequence = [] # Also clear internal sequence representation
        self.current_sequence_id = None # Reset current sequence info
        self.current_sequence_name = None
        self.current_sequence_description = None
        return True

    def add_step_to_device(self, step_config):
        """
        Adds a single test step to the device's sequence memory.
        Does NOT modify the internal self.sequence list.
        step_config is a dictionary defining the step.
        Example: {'type': 'ACW', 'voltage': '1200', 'max_limit': '5mA', ...}
        """
        if not self.device.is_open:
            print("Error: Device not open to add test step.")
            return False

        test_type = step_config.get('type', None)
        if not test_type or test_type not in TEST_TYPES:
            print(f"Error: Invalid or missing test type in step config: {test_type}")
            return False

        params = []
        try:
            if test_type == "ACW":
                voltage = step_config.get('voltage', "1000")
                ramp_time = step_config.get('ramp_time', "1.0")
                dwell_time = step_config.get('dwell_time', "2.0")
                min_limit_parsed = parse_current_input(step_config.get('min_limit', ""))
                max_limit_parsed = parse_current_input(step_config.get('max_limit', "5mA"))
                ground = "GND" if step_config.get('ground_check', False) else ""
                if min_limit_parsed is None or max_limit_parsed is None:
                    raise ValueError("Invalid current limit format")
                params = [voltage, ramp_time, dwell_time, min_limit_parsed, max_limit_parsed]
                if ground: params.append(ground)

            elif test_type == "DCW":
                voltage = step_config.get('voltage', "1000")
                ramp_time = step_config.get('ramp_time', "1.0")
                dwell_time = step_config.get('dwell_time', "2.0")
                min_limit_parsed = parse_current_input(step_config.get('min_limit', ""))
                max_limit_parsed = parse_current_input(step_config.get('max_limit', "5mA"))
                ground = "GND" if step_config.get('ground_check', False) else ""
                if min_limit_parsed is None or max_limit_parsed is None:
                     raise ValueError("Invalid current limit format")
                params = [voltage, ramp_time, dwell_time, min_limit_parsed, max_limit_parsed]
                if ground: params.append(ground)

            elif test_type == "IR":
                voltage = step_config.get('voltage', "500")
                ramp_time = step_config.get('ramp_time', "1.0")
                dwell_time = step_config.get('dwell_time', "2.0")
                min_limit = step_config.get('min_limit', "") # Assuming resistance parsing not yet implemented
                max_limit = step_config.get('max_limit', "")
                params = [voltage, ramp_time, dwell_time, min_limit, max_limit]

            elif test_type == "CONT":
                current = step_config.get('current', "0.1")
                min_limit = step_config.get('min_limit', "")
                max_limit = step_config.get('max_limit', "0.1")
                dwell_time = step_config.get('dwell_time', "1.0")
                params = [current, min_limit, max_limit, dwell_time]

            elif test_type == "GND":
                current = step_config.get('current', "10")
                max_limit = step_config.get('max_limit', "0.1")
                dwell_time = step_config.get('dwell_time', "2.0")
                freq = step_config.get('freq', "60")
                params = [current, max_limit, dwell_time, freq]

            else:
                print(f"Error: Parameter logic for test type '{test_type}' not implemented.")
                return False

        except ValueError as e:
            print(f"Error processing parameters for {test_type} step: {e}")
            return False

        # Construct the ADD command string carefully
        add_command = f"ADD,{test_type}"
        for param in params:
            add_command += ","
            add_command += str(param) # Let SCPI handle empty strings

        # Send the command
        print(f"Sending command: {add_command}")
        if not self.device.send_command(add_command):
            print("Failed to send ADD command.")
            return False

        # Check for errors immediately after
        time.sleep(0.2)
        err_status = self.device.query_command("*ERR?")
        if err_status is None:
            print("Warning: Could not verify error status after ADD command.")
            # Consider returning False if strict verification is needed
            return True # Assume success for now
        elif err_status != "0":
            print(f"Error reported by device after ADD command: {err_status}")
            print("Check parameter ranges and formats.")
            return False
        else:
            # Success - DO NOT APPEND TO self.sequence here
            print(f"ADD command for {test_type} step sent successfully to device.")
            return True

    def run_sequence(self):
        """Runs the currently configured sequence on the device and reports results."""
        if not self.device.is_open:
            print("Error: Device not open to run sequence.")
            return None # Indicate run couldn't start

        # Use the internally stored sequence length
        num_steps = len(self.sequence)
        if num_steps <= 0:
            print("No test steps configured in the application sequence. Please add steps first.")
            # Optionally, add a check here to query STEP? from device if you want to run pre-existing sequences
            # num_steps_on_device_str = self.device.query_command("STEP?") # Query *after* ensuring device is open
            # ... handle running pre-existing sequence ...
            return None

        print(f"Starting test sequence with {num_steps} configured step(s)...")
        # Clear status before running
        self.device.send_command("*CLS")
        time.sleep(0.1)

        if not self.device.send_command("RUN"):
            print("Failed to send RUN command.")
            # Check error
            err = self.device.query_command("*ERR?")
            print(f"Error status after failed RUN: {err}")
            return None

        # Poll for completion
        print("Test running... Waiting for completion...")
        max_wait_sec = 3600 # Max wait 1 hour - adjust as needed
        start_time = time.time()
        while (time.time() - start_time) < max_wait_sec:
            time.sleep(0.5) # Polling interval
            run_status = self.device.query_command("RUN?")

            if run_status == "0": # Test finished
                print("Test sequence completed.")
                break
            elif run_status == "1": # Still running
                continue
            elif run_status is None:
                print("Warning: Failed to get RUN? status during polling.")
                # Continue polling for a while longer?
            else:
                print(f"Warning: Unexpected RUN? status: {run_status}. Aborting.")
                self.device.send_command("ABORT")
                return None # Indicate abnormal finish
        else:
            # Loop finished due to timeout
            print(f"Error: Test sequence timed out after {max_wait_sec} seconds. Aborting.")
            self.device.send_command("ABORT")
            return None

        # --- Get Results --- #
        results = {'overall': None, 'steps': []}
        time.sleep(0.1)
        results['overall'] = self.device.query_command("RSLT?")

        print(f"Overall Result Code: {results['overall']} ({'PASS' if results['overall'] == '0' else 'FAIL/Other'})")

        # Use the number of steps from our internal sequence
        for i in range(1, num_steps + 1):
            step_result_str = self.device.query_command(f"STEPRSLT?,{i}")
            step_data = {'step_number': i, 'raw': step_result_str, 'parsed': None}
            if step_result_str:
                step_data['parsed'] = self._parse_step_result(step_result_str)
            results['steps'].append(step_data)

        return results # Return the structured results

    def _parse_step_result(self, result_string):
        """Parses a STEPRSLT? string into a dictionary."""
        parsed = {}
        fields = result_string.split(',')
        try:
            # Based on typical V7X STEPRSLT? format
            if len(fields) >= 6:
                parsed['term_state'] = fields[0]
                parsed['elapsed_time'] = fields[1]
                parsed['status_code'] = fields[2]
                parsed['level'] = fields[3]
                parsed['limit'] = fields[4]
                parsed['measurement'] = fields[5]
            if len(fields) >= 7:
                 # Often Max ARC for ACW/DCW
                parsed['optional1'] = fields[6]
            # Add more fields if the instrument provides them
            return parsed
        except IndexError:
            print(f"Warning: Could not parse all expected fields from '{result_string}'")
            return None # Parsing failed
        except Exception as e:
            print(f"Error parsing step result '{result_string}': {e}")
            return None

    def save_sequence_to_supabase(self, sequence_name, description=""):
        """Saves the current internal sequence to Supabase."""
        if not self.supabase_client:
            print("Error: Supabase client not available. Cannot save sequence.")
            return False, "Supabase client not initialized."
        if not self.sequence:
            print("Error: No sequence steps configured to save.")
            return False, "No sequence steps configured."
        if not sequence_name:
            return False, "Sequence name cannot be empty."

        print(f"Saving sequence '{sequence_name}' to Supabase...")
        try:
            # 1. Insert into test_sequences table
            sequence_data = {
                "sequence_name": sequence_name,
                "description": description
            }
            # Use upsert to handle potential duplicate sequence_name - needs RLS/policy allowing update
            # Or, query first to check if name exists and ask user to overwrite (more complex GUI logic)
            # For simplicity, let's try insert and handle potential unique constraint errors
            res_sequence = self.supabase_client.table("test_sequences") \
                                           .insert(sequence_data) \
                                           .execute()

            # Check for errors after insert
            if not res_sequence.data:
                 # Handle potential specific errors like unique constraint violation
                 if "duplicate key value violates unique constraint" in str(res_sequence.error):
                     error_msg = f"Sequence name '{sequence_name}' already exists."
                     print(f"Error saving sequence: {error_msg}")
                     return False, error_msg
                 else:
                    error_msg = f"Supabase error saving sequence header: {res_sequence.error}"
                    print(error_msg)
                    return False, error_msg

            # ----> Store the ID and Name <----
            self.current_sequence_id = res_sequence.data[0]['id']
            self.current_sequence_name = sequence_name
            self.current_sequence_description = description
            print(f"Sequence header saved with ID: {self.current_sequence_id}")

            # 2. Prepare and insert steps into test_steps table
            steps_to_insert = []
            for i, step_config in enumerate(self.sequence):
                # Prepare the parameters JSON - ensuring serializable data
                # Exclude internal/UI states if any, only save config needed to recreate
                params_json = json.dumps(step_config) # Basic serialization

                steps_to_insert.append({
                    "sequence_id": self.current_sequence_id,
                    "step_number": i + 1,
                    "step_type": step_config.get('type', 'UNKNOWN'),
                    "parameters": params_json
                })

            if steps_to_insert:
                res_steps = self.supabase_client.table("test_steps") \
                                                .insert(steps_to_insert) \
                                                .execute()

                if not res_steps.data:
                    error_msg = f"Supabase error saving test steps: {res_steps.error}"
                    # Attempt to delete the sequence header we just created?
                    print(f"Error: {error_msg}. Rolling back sequence header is recommended.")
                    try:
                         self.supabase_client.table("test_sequences").delete().eq('id', self.current_sequence_id).execute()
                         print(f"Rolled back sequence header ID: {self.current_sequence_id}")
                    except Exception as del_e:
                         print(f"Failed to rollback sequence header: {del_e}")
                    # Clear stored ID/Name on failure
                    self.current_sequence_id = None
                    self.current_sequence_name = None
                    self.current_sequence_description = None
                    return False, error_msg

            print(f"Successfully saved {len(steps_to_insert)} steps for sequence '{sequence_name}'.")
            return True, "Sequence saved successfully."

        except Exception as e:
            error_msg = f"An unexpected error occurred during save: {e}"
            print(error_msg)
            # Attempt rollback if sequence_id was obtained?
            self.current_sequence_id = None # Clear on exception
            self.current_sequence_name = None
            self.current_sequence_description = None
            return False, error_msg

    def list_saved_sequences(self):
        """Retrieves a list of saved sequence names from Supabase."""
        if not self.supabase_client:
            print("Error: Supabase client not available.")
            return []
        try:
            res = self.supabase_client.table("test_sequences") \
                                      .select("id, sequence_name, description") \
                                      .order("sequence_name") \
                                      .execute()
            if res.data:
                # Return list of tuples (name, id, description)
                return [(item['sequence_name'], item['id'], item.get('description', '')) for item in res.data]
            else:
                print(f"Could not list sequences: {res.error}")
                return []
        except Exception as e:
            print(f"Error listing sequences from Supabase: {e}")
            return []

    def load_sequence_from_supabase(self, sequence_id):
        """Loads a sequence and its steps from Supabase using the sequence ID."""
        if not self.supabase_client:
            print("Error: Supabase client not available.")
            return None
        if sequence_id is None:
            print("Error: Invalid sequence ID provided.")
            return None

        print(f"Loading sequence with ID: {sequence_id} from Supabase...")
        try:
            # 1. Get sequence header info (optional, maybe just name?)
            res_seq = self.supabase_client.table("test_sequences") \
                                          .select("sequence_name, description") \
                                          .eq("id", sequence_id) \
                                          .maybe_single() \
                                          .execute()
            if not res_seq.data:
                 print(f"Error: Sequence with ID {sequence_id} not found.")
                 # Reset current sequence info on load failure
                 self.sequence = []
                 self.current_sequence_id = None
                 self.current_sequence_name = None
                 self.current_sequence_description = None
                 return None
            sequence_name = res_seq.data.get('sequence_name', 'Unknown')
            sequence_description = res_seq.data.get('description', '')
            print(f"Found sequence: '{sequence_name}'")

            # 2. Get all steps for this sequence, ordered by step_number
            res_steps = self.supabase_client.table("test_steps") \
                                            .select("step_number, step_type, parameters") \
                                            .eq("sequence_id", sequence_id) \
                                            .order("step_number") \
                                            .execute()

            if not res_steps.data:
                print(f"Warning: No steps found for sequence ID {sequence_id}.")
                # Return empty sequence or None?
                loaded_sequence = [] # Return an empty sequence
            else:
                print(f"Found {len(res_steps.data)} steps.")
                loaded_sequence = []
                for step_row in res_steps.data:
                    try:
                        # Parse the JSON parameters back into a dictionary
                        step_params_json = step_row.get('parameters')
                        if isinstance(step_params_json, str): # Ensure it's a string before parsing
                            step_config = json.loads(step_params_json)
                        elif isinstance(step_params_json, dict): # If already parsed by driver
                            step_config = step_params_json
                        else:
                             raise ValueError("Unexpected type for parameters field")

                        # Basic validation/structure check
                        if 'type' not in step_config:
                             step_config['type'] = step_row.get('step_type', 'UNKNOWN')
                        # Add step_number if not stored in JSON?
                        # step_config['step_number'] = step_row.get('step_number')

                        loaded_sequence.append(step_config)
                    except json.JSONDecodeError as json_e:
                        print(f"Error decoding JSON parameters for step {step_row.get('step_number')}: {json_e}")
                        # Skip this step or fail loading?
                        continue # Skip malformed step
                    except ValueError as val_e:
                         print(f"Error processing parameters for step {step_row.get('step_number')}: {val_e}")
                         continue # Skip malformed step

            # Update the internal sequence *after* successful loading
            self.sequence = loaded_sequence
            # ----> Store the loaded ID and Name <----
            self.current_sequence_id = sequence_id
            self.current_sequence_name = sequence_name
            self.current_sequence_description = sequence_description
            print(f"Sequence '{sequence_name}' loaded successfully with {len(self.sequence)} steps.")
            return self.sequence # Return the loaded sequence list

        except Exception as e:
            print(f"An unexpected error occurred loading sequence: {e}")
            # Reset current sequence info on load failure
            self.sequence = []
            self.current_sequence_id = None
            self.current_sequence_name = None
            self.current_sequence_description = None
            return None 
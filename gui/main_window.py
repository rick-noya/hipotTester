import sys
import time # Import the time module
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QStatusBar,
    QGroupBox, QFormLayout, QListWidget, QListWidgetItem,
    QMenuBar, QMessageBox, QInputDialog, QDialog, QDialogButtonBox,
    QComboBox
)
from PySide6.QtGui import QAction, QColor
from PySide6.QtCore import Qt, Signal, QObject, QThread

# Import device and sequencer (assuming they are in sibling directories)
import os
# Add parent directory to path to allow imports like device.v7x_device
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from device.v7x_device import V7xDevice, V7xDeviceError
from testing.test_sequencer import TestSequencer
from utils.constants import TEST_TYPES, STATUS_FLAGS, TERMINATION_STATES

# Import the setup dialog
from gui.test_setup_dialog import TestSetupDialog

# Import Supabase client utility
from utils.supabase_client import get_supabase_client

# Worker for running tests in a separate thread
class TestWorker(QObject):
    finished = Signal(object) # Signal to emit results (or None on error)
    progress = Signal(str)    # Signal for status updates

    def __init__(self, sequencer: TestSequencer):
        super().__init__()
        self.sequencer = sequencer

    def run(self):
        try:
            self.progress.emit("Starting test sequence...")
            results = self.sequencer.run_sequence()
            self.finished.emit(results)
        except Exception as e:
            self.progress.emit(f"Error during test run: {e}")
            self.finished.emit(None) # Indicate error

# --- Load Sequence Dialog --- #
class LoadSequenceDialog(QDialog):
    def __init__(self, sequences, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Test Sequence")
        self.sequences = sequences # List of tuples (name, id)
        self.selected_id = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a sequence to load:"))

        self.list_widget = QListWidget()
        for name, seq_id in self.sequences:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, seq_id) # Store ID in item data
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self.accept_selection)
        layout.addWidget(self.list_widget)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept_selection)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def accept_selection(self):
        selected_item = self.list_widget.currentItem()
        if selected_item:
            self.selected_id = selected_item.data(Qt.UserRole)
            self.accept()
        else:
            # No selection, treat as cancel or show message?
            self.reject()

    def get_selected_sequence_id(self):
        return self.selected_id

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("V7X Control Panel")
        self.setGeometry(100, 100, 800, 600)

        self.device = None
        self.sequencer = None
        self.test_thread = None
        self.test_worker = None

        self.supabase_client = get_supabase_client()

        self._create_widgets()
        self._create_layout()
        self._create_menu()
        self._connect_signals()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Disconnected")

        self._initialize_device()

    def _initialize_device(self):
        try:
            self.device = V7xDevice(debug=False) # Set debug=True for more logs
            if not self.device._dll: # Check if DLL loaded
                 self.show_error("Device Initialization Failed", "DLL could not be loaded. Check path and compatibility.")
                 self.connect_button.setEnabled(False)
                 return

            self.sequencer = TestSequencer(self.device)

            # Initialize Supabase Client
            self.supabase_client = get_supabase_client()
            # Load operators *after* client is initialized
            if self.supabase_client:
                self._load_operator_names()

            # Check connection *after* UI elements potentially reliant on Supabase are ready
            self.check_connection()

        except V7xDeviceError as e:
            self.show_error("Device Initialization Error", str(e))
            self.connect_button.setEnabled(False)
        except Exception as e:
            self.show_error("Unexpected Error", f"An unexpected error occurred during initialization: {e}")
            self.connect_button.setEnabled(False)

    def _create_widgets(self):
        # Connection
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        self.connection_status_label = QLabel("Status: Disconnected")
        self.connection_status_label.setStyleSheet("color: red")

        # Direct Command
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Enter SCPI command (e.g., *IDN?)")
        self.send_command_button = QPushButton("Send")
        self.command_response_output = QTextEdit()
        self.command_response_output.setReadOnly(True)
        self.clear_log_button = QPushButton("Clear Log")

        # Test Sequence
        self.sequence_list_widget = QListWidget()
        self.add_step_button = QPushButton("Add Step...")
        self.clear_sequence_button = QPushButton("Clear Sequence")
        self.run_test_button = QPushButton("Run Test Sequence")
        self.run_test_button.setStyleSheet("background-color: lightgreen")

        # Test Results
        self.results_output = QTextEdit()
        self.results_output.setReadOnly(True)

        # Enable/disable based on connection status
        self.send_command_button.setEnabled(False)
        self.add_step_button.setEnabled(False)
        self.clear_sequence_button.setEnabled(False)
        self.run_test_button.setEnabled(False)

        # --- Test Context Group --- #
        self.dut_serial_input = QLineEdit()
        self.operator_name_combo = QComboBox()
        self.operator_name_combo.setEditable(True) # Allow adding new names temporarily?
        self.operator_name_combo.setPlaceholderText("Select or type Operator")
        self.sequence_name_input = QLineEdit()

    def _create_layout(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # --- Connection Group --- #
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(self.connect_button)
        conn_layout.addWidget(self.disconnect_button)
        conn_layout.addWidget(self.connection_status_label)
        conn_layout.addStretch()
        conn_group.setLayout(conn_layout)

        # --- Test Context Group --- #
        context_group = QGroupBox("Test Context")
        context_layout = QFormLayout()
        context_layout.addRow("DUT Serial Number:", self.dut_serial_input)
        context_layout.addRow("Operator Name:", self.operator_name_combo)
        context_layout.addRow("Sequence Name:", self.sequence_name_input)
        context_group.setLayout(context_layout)

        # --- Direct Command Group --- #
        cmd_group = QGroupBox("Direct Command")
        cmd_layout = QVBoxLayout()
        cmd_input_layout = QHBoxLayout()
        cmd_input_layout.addWidget(QLabel("Command:"))
        cmd_input_layout.addWidget(self.command_input)
        cmd_input_layout.addWidget(self.send_command_button)
        cmd_layout.addLayout(cmd_input_layout)
        cmd_layout.addWidget(QLabel("Response/Log:"))
        cmd_layout.addWidget(self.command_response_output)
        cmd_layout.addWidget(self.clear_log_button, alignment=Qt.AlignRight)
        cmd_group.setLayout(cmd_layout)

        # --- Test Sequence Group --- #
        seq_group = QGroupBox("Test Sequence")
        seq_layout = QVBoxLayout()
        seq_layout.addWidget(QLabel("Configured Steps:"))
        seq_layout.addWidget(self.sequence_list_widget)
        seq_buttons_layout = QHBoxLayout()
        seq_buttons_layout.addWidget(self.add_step_button)
        seq_buttons_layout.addWidget(self.clear_sequence_button)
        seq_buttons_layout.addStretch()
        seq_buttons_layout.addWidget(self.run_test_button)
        seq_layout.addLayout(seq_buttons_layout)
        seq_group.setLayout(seq_layout)

        # --- Test Results Group --- #
        res_group = QGroupBox("Test Results")
        res_layout = QVBoxLayout()
        res_layout.addWidget(self.results_output)
        res_group.setLayout(res_layout)

        # Add groups to main layout
        main_layout.addWidget(conn_group)
        main_layout.addWidget(context_group)
        main_layout.addWidget(cmd_group)
        main_layout.addWidget(seq_group)
        main_layout.addWidget(res_group)

        self.setCentralWidget(central_widget)

    def _create_menu(self):
        menu_bar = self.menuBar()
        # File Menu
        file_menu = menu_bar.addMenu("&File")

        save_action = QAction("&Save Sequence...", self)
        save_action.triggered.connect(self.save_sequence)
        load_action = QAction("&Load Sequence...", self)
        load_action.triggered.connect(self.load_sequence)

        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(save_action)
        file_menu.addAction(load_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        # Device Menu
        device_menu = menu_bar.addMenu("&Device")
        connect_action = QAction("&Connect", self)
        connect_action.triggered.connect(self.connect_device)
        disconnect_action = QAction("&Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect_device)
        reset_action = QAction("*&RST", self)
        reset_action.triggered.connect(lambda: self.send_direct_command("*RST"))
        idn_action = QAction("*IDN?", self)
        idn_action.triggered.connect(lambda: self.send_direct_command("*IDN?"))
        device_menu.addAction(connect_action)
        device_menu.addAction(disconnect_action)
        device_menu.addSeparator()
        device_menu.addAction(reset_action)
        device_menu.addAction(idn_action)

        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _connect_signals(self):
        self.connect_button.clicked.connect(self.connect_device)
        self.disconnect_button.clicked.connect(self.disconnect_device)
        self.send_command_button.clicked.connect(self.send_direct_command_from_input)
        self.clear_log_button.clicked.connect(self.command_response_output.clear)
        self.add_step_button.clicked.connect(self.open_test_setup_dialog)
        self.clear_sequence_button.clicked.connect(self.clear_sequence)
        self.run_test_button.clicked.connect(self.run_test)

    # --- Device Connection --- #

    def check_connection(self):
        if self.device and self.device.find_device() > 0:
            self.log_message("Device detected. Attempting connection...")
            self.connect_device()
        else:
            self.log_message("No V7X device detected on startup.")
            self.update_ui_connection_state(False)

    def connect_device(self):
        if not self.device:
             self.log_message("Device object not initialized.")
             return
        if self.device.is_open:
            self.log_message("Device already connected.")
            return

        self.status_bar.showMessage("Connecting...")
        self.log_message("Attempting to connect...")
        if self.device.open():
            self.log_message("Device connected successfully.")
            self.update_ui_connection_state(True)
            # Query IDN on connect
            self.send_direct_command("*IDN?")
        else:
            self.log_message("Failed to connect to device.")
            self.show_error("Connection Failed", "Could not open the V7X device. Check logs.")
            self.update_ui_connection_state(False)

    def disconnect_device(self):
        if not self.device or not self.device.is_open:
            self.log_message("Device is not connected.")
            return

        self.status_bar.showMessage("Disconnecting...")
        if self.device.close():
            self.log_message("Device disconnected.")
        else:
            self.log_message("Error during disconnection.")
        self.update_ui_connection_state(False)

    def update_ui_connection_state(self, connected: bool):
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.send_command_button.setEnabled(connected)
        self.add_step_button.setEnabled(connected)
        self.clear_sequence_button.setEnabled(connected)
        self.run_test_button.setEnabled(connected)

        if connected:
            self.connection_status_label.setText("Status: Connected")
            self.connection_status_label.setStyleSheet("color: green")
            self.status_bar.showMessage("Connected")
        else:
            self.connection_status_label.setText("Status: Disconnected")
            self.connection_status_label.setStyleSheet("color: red")
            self.status_bar.showMessage("Disconnected")

    # --- Direct Commands --- #

    def send_direct_command_from_input(self):
        command = self.command_input.text().strip()
        if command:
            self.send_direct_command(command)
            self.command_input.clear()
        else:
            self.log_message("No command entered.")

    def send_direct_command(self, command):
        if not self.device or not self.device.is_open:
            self.log_message("Error: Device not connected.")
            return

        self.log_message(f"Sending: {command}")
        QApplication.processEvents() # Keep UI responsive

        is_query = command.endswith('?')
        if is_query:
            response = self.device.query_command(command)
            if response is not None:
                self.log_message(f"Response: {response}")
            else:
                self.log_message("No response received or error occurred.")
        else:
            if self.device.send_command(command):
                self.log_message("Command sent successfully.")
                # Optional: Check error after non-query commands
                time.sleep(0.1)
                err = self.device.query_command("*ERR?")
                if err is not None and err != "0":
                     self.log_message(f"Device reported error: {err}")
            else:
                self.log_message("Failed to send command.")

    # --- Test Sequence Handling --- #

    def open_test_setup_dialog(self):
        if not self.sequencer:
             self.log_message("Sequencer not initialized.")
             return
        if not self.device or not self.device.is_open:
             self.show_error("Add Step Error", "Device must be connected to add steps.")
             return

        dialog = TestSetupDialog(list(TEST_TYPES.keys()), self)
        if dialog.exec():
            step_config = dialog.get_step_config()
            if step_config:
                self.log_message(f"Attempting to add step: {step_config}")
                # Call the renamed method to send to device
                if self.sequencer.add_step_to_device(step_config):
                    # Append to the *local* list only after successful add to device
                    self.sequencer.sequence.append(step_config)
                    self.log_message("Step added successfully to device and local sequence.")
                    self.update_sequence_list()
                else:
                    self.log_message("Failed to add step to device. Check parameters and device errors.")
                    self.show_error("Add Step Failed", "Could not add step to the device sequence. Check logs.")

    def update_sequence_list(self):
        self.sequence_list_widget.clear()
        if not self.sequencer:
             return
        for i, step in enumerate(self.sequencer.sequence):
             step_type = step.get('type', 'Unknown')
             step_name = step.get('step_name', '')

             # Format the display string
             display_name = f"Step {i+1}: {step_type}"
             if step_name:
                 display_name += f" - {step_name}"

             item = QListWidgetItem(display_name)
             # Store the step index or config in the item if needed for editing/deleting later
             item.setData(Qt.UserRole, i) # Store index for potential future use
             self.sequence_list_widget.addItem(item)

    def clear_sequence(self):
        if not self.sequencer:
             self.log_message("Sequencer not initialized.")
             return

        reply = QMessageBox.question(self, "Confirm Clear",
                                     "Are you sure you want to clear the test sequence on the device?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.log_message("Clearing sequence...")
            if self.sequencer.clear_sequence_on_device():
                self.log_message("Sequence cleared successfully.")
                self.update_sequence_list()
                self.results_output.clear()
            else:
                self.log_message("Failed to clear sequence on device.")
                self.show_error("Clear Failed", "Could not clear sequence on device. Check logs.")

    # --- Running Tests --- #

    def run_test(self):
        if not self.sequencer or not self.device or not self.device.is_open:
            self.show_error("Run Error", "Device not connected or sequencer not ready.")
            return
        if not self.sequencer.sequence:
             # Optionally, query device steps here?
             reply = QMessageBox.question(self, "Run Test", "Local sequence is empty. Run sequence currently on device?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
             if reply == QMessageBox.StandardButton.No:
                  return
            # If yes, proceed to run whatever is on the device

        self.results_output.clear()
        self.run_test_button.setEnabled(False)
        self.status_bar.showMessage("Running test...")

        # Run in a separate thread
        self.test_thread = QThread()
        self.test_worker = TestWorker(self.sequencer)
        self.test_worker.moveToThread(self.test_thread)

        # Connect signals
        self.test_worker.finished.connect(self.handle_test_results)
        self.test_worker.progress.connect(self.log_message)
        self.test_thread.started.connect(self.test_worker.run)
        self.test_worker.finished.connect(self.test_thread.quit)
        self.test_worker.finished.connect(self.test_worker.deleteLater)
        self.test_thread.finished.connect(self.test_thread.deleteLater)

        self.test_thread.start()

    def handle_test_results(self, results):
        self.run_test_button.setEnabled(True) # Re-enable button
        if results:
            self.log_message("Test finished. Processing results...")
            self.display_results(results)
            self.status_bar.showMessage("Test Complete")

            # Log results to Supabase if successful and client available
            if self.supabase_client:
                self.log_to_supabase(results)
        else:
            self.log_message("Test failed or was aborted.")
            self.show_error("Test Execution Failed", "The test sequence did not complete successfully. Check logs.")
            self.status_bar.showMessage("Test Failed")

        # Wait for the thread to fully finish before cleaning up
        if self.test_thread and self.test_thread.isRunning():
            self.test_thread.quit() # Signal thread to stop event loop
            self.test_thread.wait(2000) # Wait up to 2 seconds for it to finish

        # Clean up thread references
        self.test_thread = None
        self.test_worker = None

    def display_results(self, results):
        self.results_output.clear()
        overall_status_code = results.get('overall', '?')

        overall_pass = (overall_status_code == '0')
        overall_text = "PASS" if overall_pass else f"FAIL/Other ({overall_status_code})"

        # Use HTML for basic formatting (bold, color)
        self.results_output.append(f"<b>** Overall Result: <font color='{'green' if overall_pass else 'red'}'>{overall_text}</font> **</b><br>")

        # Display overall status flags if failed
        if not overall_pass:
            try:
                code_int = int(overall_status_code)
                flags_present = []
                for flag_bit, description in STATUS_FLAGS.items():
                    if code_int & flag_bit:
                        flags_present.append(f"- {description} (Bit {flag_bit})")
                if flags_present:
                    self.results_output.append("<b>Overall Failure Reasons:</b>")
                    self.results_output.append("<br>".join(flags_present))
                    self.results_output.append("<br>") # Extra space
            except ValueError:
                pass # Could not parse overall code as integer

        for step_res in results.get('steps', []):
            step_num = step_res.get('step_number', '?')
            raw = step_res.get('raw', 'N/A')
            parsed = step_res.get('parsed')

            self.results_output.append(f"<b>--- Step {step_num} ---</b> ")
            if parsed:
                step_pass = (parsed.get('status_code', '-1') == '0')
                status_color = 'green' if step_pass else 'red'

                # Termination State
                term_code = parsed.get('term_state', '?')
                term_desc = TERMINATION_STATES.get(term_code, f"Unknown Code ({term_code})")
                self.results_output.append(f"  Termination      : {term_desc}")

                # Status Code and Flags
                status_code = parsed.get('status_code', '?')
                self.results_output.append(f"  Status Code      : <font color='{status_color}'>{status_code}</font>")
                if not step_pass:
                    try:
                        code_int = int(status_code)
                        step_flags = []
                        for flag_bit, description in STATUS_FLAGS.items():
                            if code_int & flag_bit:
                                step_flags.append(f"    - {description}")
                        if step_flags:
                            self.results_output.append("  Failure Reasons:")
                            self.results_output.append("<br>".join(step_flags))
                    except ValueError:
                         self.results_output.append("  (Could not parse status flags)")

                # Other parsed fields
                key_order = ['elapsed_time', 'level', 'limit', 'measurement', 'optional1'] # Control display order
                for key in key_order:
                    if key in parsed and key not in ['term_state', 'status_code']:
                        value = parsed[key]
                        key_str = key.replace('_', ' ').title()
                        # Add units where appropriate (simple example)
                        unit = " s" if key == 'elapsed_time' else ""
                        unit = " A" if key == 'optional1' else unit # Assume arc for optional1
                        self.results_output.append(f"  {key_str:<15} : {value}{unit}")

            else:
                 self.results_output.append(f"  Raw Data: {raw}")
                 self.results_output.append("  <i>(Could not parse results)</i>")
            self.results_output.append("<br>") # Add a blank line

    def log_to_supabase(self, results):
        self.log_message("Attempting to log results to Supabase...")
        dut_serial = self.dut_serial_input.text().strip() or None
        # Get selected operator name from ComboBox
        operator_name = self.operator_name_combo.currentText().strip() or None
        sequence_id = self.sequencer.current_sequence_id

        if sequence_id is None:
            self.log_message("Warning: No sequence ID available (sequence not saved/loaded?). Skipping Supabase log.")
            return

        overall_status_code = results.get('overall', '?')
        overall_result_text = 'PASS' if overall_status_code == '0' else 'FAIL'
        records_to_insert = []
        for step_res in results.get('steps', []):
            step_num = step_res.get('step_number', 0)
            parsed = step_res.get('parsed')
            raw_result = step_res.get('raw', '')
            step_config = self.sequencer.sequence[step_num - 1] if step_num > 0 and step_num <= len(self.sequencer.sequence) else {}
            test_type = step_config.get('type', 'UNKNOWN')

            record = {
                "sequence_id": sequence_id,
                "dut_serial_number": dut_serial,
                "operator_name": operator_name,
                "overall_result": overall_result_text,
                "step_number": step_num,
                "test_step_type": test_type,
                "termination_state_code": None,
                "termination_state_text": None,
                "elapsed_time_seconds": None,
                "status_code": None,
                "status_description": None,
                "test_level": None,
                "test_level_unit": None,
                "breakdown_current_peak": None,
                "measurement_result": None,
                "measurement_unit": None,
                "arc_current_peak": None,
                "notes": f"Raw: {raw_result}"
            }

            if parsed:
                try:
                    term_code_str = parsed.get('term_state')
                    record["termination_state_code"] = int(term_code_str) if term_code_str and term_code_str != '?' else None
                    record["termination_state_text"] = TERMINATION_STATES.get(term_code_str, None)

                    elapsed_str = parsed.get('elapsed_time')
                    record["elapsed_time_seconds"] = float(elapsed_str) if elapsed_str else None

                    status_code_str = parsed.get('status_code')
                    record["status_code"] = int(status_code_str) if status_code_str and status_code_str != '?' else 0

                    # Generate status description
                    status_desc_list = []
                    if record["status_code"] != 0:
                        for flag_bit, description in STATUS_FLAGS.items():
                            if record["status_code"] & flag_bit:
                                status_desc_list.append(description)
                    record["status_description"] = ", ".join(status_desc_list) if status_desc_list else ("PASS" if record["status_code"] == 0 else None)

                    level_str = parsed.get('level')
                    record["test_level"] = float(level_str) if level_str else None
                    # Determine unit based on test type (simplistic)
                    if test_type in ["ACW", "DCW", "IR"]:
                        record["test_level_unit"] = 'V'
                    elif test_type in ["CONT", "GND"]:
                         record["test_level_unit"] = 'A'

                    measurement_str = parsed.get('measurement')
                    record["measurement_result"] = float(measurement_str) if measurement_str else None
                    if test_type in ["ACW", "DCW", "GND"]:
                        record["measurement_unit"] = 'A' if test_type != "GND" else 'Ohms' # GND measurement is resistance
                    elif test_type in ["IR", "CONT"]:
                         record["measurement_unit"] = 'Ohms'

                    # Map optional fields (assuming common positions)
                    if 'optional1' in parsed:
                        if test_type in ["ACW", "DCW"]:
                            arc_str = parsed['optional1']
                            record["arc_current_peak"] = float(arc_str) if arc_str else None

                except (ValueError, TypeError) as e:
                    self.log_message(f"Error converting step {step_num} results for Supabase: {e}")
                    record["notes"] += f" | PARSE_ERROR: {e}"

            records_to_insert.append(record)

        if records_to_insert:
            try:
                data, count = self.supabase_client.table('vitrek_test_results').insert(records_to_insert).execute()
                if hasattr(data, '__len__') and len(data) > 1 and data[1]:
                    self.log_message(f"Successfully logged {len(data[1])} step result(s) to Supabase.")
                else:
                    error_info = data[0] if hasattr(data, '__len__') and data else data
                    self.log_message(f"Failed to log results to Supabase. Response: {error_info}")
                    self.show_error("Supabase Log Failed", f"Could not log results. Response: {error_info}")
            except Exception as e:
                self.log_message(f"Error inserting data into Supabase: {e}")
                self.show_error("Supabase Error", f"An exception occurred while logging results: {e}")
        else:
             self.log_message("No valid records generated to log to Supabase.")

    # --- Save/Load Sequence --- #
    def save_sequence(self):
        if not self.sequencer or not self.device or not self.device.is_open:
            self.show_error("Save Error", "Device must be connected to save.")
            return
        if not self.sequencer.sequence:
            self.show_error("Save Error", "No steps in the current sequence to save.")
            return

        # Prompt for sequence name
        # Use current sequence name input field as default?
        default_name = self.sequence_name_input.text().strip()
        seq_name, ok = QInputDialog.getText(self, "Save Sequence",
                                            "Enter a unique name for this sequence:",
                                            QLineEdit.EchoMode.Normal,
                                            default_name)

        if ok and seq_name:
            self.log_message(f"Saving sequence as '{seq_name}'...")
            # Optional: Add description input?
            description = ""
            success, message = self.sequencer.save_sequence_to_supabase(seq_name, description)
            if success:
                self.log_message(message)
                # Update sequence name input field?
                self.sequence_name_input.setText(seq_name)
                QMessageBox.information(self, "Save Successful", message)
            else:
                self.log_message(f"Save failed: {message}")
                self.show_error("Save Failed", message)
        elif ok: # Name was empty
             self.show_error("Save Failed", "Sequence name cannot be empty.")
        else:
             self.log_message("Save cancelled by user.")

    def load_sequence(self):
        if not self.sequencer or not self.device or not self.device.is_open:
             self.show_error("Load Error", "Device must be connected to load.")
             return
        if not self.sequencer.supabase_client:
              self.show_error("Load Error", "Supabase client not available.")
              return

        self.log_message("Fetching saved sequences...")
        saved_sequences = self.sequencer.list_saved_sequences()

        if not saved_sequences:
            QMessageBox.information(self, "Load Sequence", "No saved sequences found in Supabase.")
            self.log_message("No saved sequences found.")
            return

        dialog = LoadSequenceDialog(saved_sequences, self)
        if dialog.exec():
            sequence_id = dialog.get_selected_sequence_id()
            if sequence_id is not None:
                self.log_message(f"Loading sequence ID: {sequence_id}...")

                # Clear existing sequence before loading - Confirmation Prompt
                reply = QMessageBox.question(self, "Confirm Load",
                                     "Clear the current sequence before loading?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Yes)
                if reply == QMessageBox.StandardButton.Cancel:
                     self.log_message("Load cancelled.")
                     return
                if reply == QMessageBox.StandardButton.Yes:
                     if not self.sequencer.clear_sequence_on_device():
                         self.show_error("Load Error", "Failed to clear existing sequence on device before loading.")
                         return
                     # Sequencer.sequence is cleared inside clear_sequence_on_device
                     self.update_sequence_list() # Update UI
                     self.results_output.clear()
                else:
                    # If user chose No, we need to ensure the local list matches the device (or warn)
                    # For simplicity now, let's just clear the local list if not clearing device
                    self.sequencer.sequence = []
                    self.update_sequence_list()

                # Load the sequence structure from Supabase (doesn't touch device yet)
                loaded_sequence_list = self.sequencer.load_sequence_from_supabase(sequence_id)

                if loaded_sequence_list is not None:
                    # self.sequencer.sequence is now updated by load_sequence_from_supabase
                    self.log_message("Sequence structure loaded successfully from Supabase.")

                    # Now, program the loaded sequence onto the device hardware
                    self.log_message("Programming loaded steps onto device hardware...")
                    steps_programmed_count = 0
                    # Iterate through the newly loaded self.sequencer.sequence
                    for step_config in self.sequencer.sequence:
                         # Call the renamed method to add to device
                         if self.sequencer.add_step_to_device(step_config):
                              steps_programmed_count += 1
                         else:
                              self.show_error("Load Error", f"Failed to program step {steps_programmed_count + 1} to device hardware. Sequence on device may be incomplete.")
                              break # Stop programming if one fails
                    self.log_message(f"Programmed {steps_programmed_count} steps to device.")

                    # Update UI list based on the loaded sequence (already in self.sequencer.sequence)
                    self.update_sequence_list()
                    # Update sequence name field using the name now stored in sequencer
                    if self.sequencer.current_sequence_name:
                        self.sequence_name_input.setText(self.sequencer.current_sequence_name)
                    else: # Fallback if name wasn't stored somehow
                        for name, sid in saved_sequences:
                             if sid == sequence_id:
                                  self.sequence_name_input.setText(name)
                                  break
                else:
                    self.show_error("Load Failed", "Could not load sequence details from Supabase.")
            else:
                 self.log_message("No sequence selected.")
        else:
             self.log_message("Load cancelled.")

    # --- Utility Methods --- #

    def log_message(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.command_response_output.append(f"[{timestamp}] {message}")
        # Scroll to the bottom
        self.command_response_output.verticalScrollBar().setValue(
            self.command_response_output.verticalScrollBar().maximum()
        )
        print(f"LOG: {message}") # Also print to console for debugging

    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)
        self.log_message(f"ERROR: {title} - {message}")

    def show_about(self):
        QMessageBox.about(self, "About V7X Control Panel",
                          "A simple GUI application to control Vitrek V7X devices.\n" +
                          f"DLL Version: {self.device.get_library_version() if self.device else 'N/A'}")

    def closeEvent(self, event):
        # Ensure device is closed when window is closed
        if self.device and self.device.is_open:
            print("Closing device connection on exit...")
            self.device.close()
        event.accept() # Allow window to close

    def _load_operator_names(self):
        """Fetch user names from the Supabase users table and populate the combo box."""
        if not self.supabase_client:
            self.log_message("Supabase not configured, cannot load operator names.")
            return

        self.log_message("Loading operator names from Supabase...")
        try:
            response = self.supabase_client.table("users").select("user").execute()
            if response.data:
                self.operator_name_combo.clear()
                operators = sorted([item['user'] for item in response.data if item.get('user')])
                self.operator_name_combo.addItems(operators)
                self.log_message(f"Loaded {len(operators)} operator names.")
                if operators: # Select the first one by default if list is not empty
                     self.operator_name_combo.setCurrentIndex(0)
            else:
                self.log_message(f"Could not fetch operator names: {response.error}")
                self.operator_name_combo.clear()
                self.operator_name_combo.setPlaceholderText("Failed to load operators")
        except Exception as e:
            self.log_message(f"Error loading operators from Supabase: {e}")
            self.show_error("Supabase Error", f"Could not load operator names: {e}")
            self.operator_name_combo.setPlaceholderText("Error loading operators")

if __name__ == '__main__':
    # This check is important for multiprocessing/QThread safety on some platforms
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 
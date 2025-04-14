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
from PySide6.QtCore import Qt, Signal, QObject, QThread, Slot

# Import device and sequencer (assuming they are in sibling directories)
import os
# Add parent directory to path to allow imports like device.v7x_device
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from device.v7x_device import V7xDevice, V7xDeviceError
from testing.test_sequencer import TestSequencer
from utils.constants import TEST_TYPES, STATUS_FLAGS, TERMINATION_STATES

# Import the setup dialog
from gui.test_setup_dialog import TestSetupDialog

# Import LoginDialog
from gui.login_dialog import LoginDialog
from gui.profile_dialog import ProfileDialog

# Import Supabase client utility
from utils.supabase_client import get_supabase_client, get_current_user, save_session, clear_session

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
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.sequences = sequences # List of tuples (name, id, description)
        self.selected_id = None

        layout = QVBoxLayout(self)
        
        # Top section for instructions
        layout.addWidget(QLabel("Select a sequence to load:"))

        # Split layout for list and description
        split_layout = QHBoxLayout()
        
        # Left side: sequence list
        list_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        for name, seq_id, description in self.sequences:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, seq_id) # Store ID in item data
            item.setData(Qt.UserRole + 1, description) # Store description in item data
            self.list_widget.addItem(item)
        self.list_widget.itemSelectionChanged.connect(self.update_description)
        self.list_widget.itemDoubleClicked.connect(self.accept_selection)
        list_layout.addWidget(self.list_widget)
        split_layout.addLayout(list_layout)
        
        # Right side: description
        desc_layout = QVBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        self.description_display = QTextEdit()
        self.description_display.setReadOnly(True)
        self.description_display.setPlaceholderText("Select a sequence to view its description")
        desc_layout.addWidget(self.description_display)
        split_layout.addLayout(desc_layout)
        
        # Add the split layout to the main layout
        layout.addLayout(split_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept_selection)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
        # Default: select the first item if any
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
    
    def update_description(self):
        """Update the description text based on the selected sequence"""
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            selected_item = selected_items[0]
            description = selected_item.data(Qt.UserRole + 1) or ""
            self.description_display.setText(description)
        else:
            self.description_display.clear()

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
        self.current_user = None
        self.user_profile = {}
        self.operator_name_label = None

        self.supabase_client = get_supabase_client()

        self._create_widgets()
        self._create_layout()
        self._create_menu()
        self._connect_signals()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Disconnected")

        self._initialize_device()
        self._update_auth_ui()

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
            
            # Check for existing user session
            if self.supabase_client:
                self.current_user = get_current_user()
                if self.current_user:
                    # Access email as an attribute
                    user_email = getattr(self.current_user, 'email', 'Unknown')
                    self.log_message(f"Restored session for user: {user_email}")
                    
                    # Fetch profile data for the restored user
                    try:
                        user_id = getattr(self.current_user, 'id', None)
                        if user_id:
                            response = self.supabase_client.table("profiles") \
                                .select("first_name, last_name, phone_number") \
                                .eq("id", user_id) \
                                .maybe_single() \
                                .execute()
                            
                            if response.data:
                                self.user_profile = response.data
                            else:
                                self.user_profile = {}
                    except Exception as e:
                        self.log_message(f"Error fetching profile during session restore: {e}")
                        self.user_profile = {}

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
        
        # Authentication
        self.login_button = QPushButton("Login")
        self.profile_button = QPushButton("Profile")
        self.profile_button.setEnabled(False)
        self.logout_button = QPushButton("Logout")
        self.logout_button.setEnabled(False)
        self.user_label = QLabel("Not logged in")
        self.user_label.setStyleSheet("color: gray")

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
        # Add widget for step details
        self.step_details_output = QTextEdit()
        self.step_details_output.setReadOnly(True)
        self.step_details_output.setPlaceholderText("Select a step on the left to see details.")

        # Test Results
        self.results_output = QTextEdit()
        self.results_output.setReadOnly(True)

        # Enable/disable based on connection status
        self.send_command_button.setEnabled(False)
        self.add_step_button.setEnabled(False)
        self.clear_sequence_button.setEnabled(False)
        self.run_test_button.setEnabled(False)

        # --- Test Context Group --- # Renamed DUT field
        self.assemblage_input = QLineEdit()
        self.assemblage_input.setPlaceholderText("Scan Assemblage Barcode ID here") # Updated placeholder
        self.operator_name_combo = QComboBox()
        self.operator_name_combo.setEditable(True)
        self.operator_name_combo.setPlaceholderText("Select or type Operator")
        self.operator_name_label = QLabel("Operator: Not logged in")
        self.operator_name_label.setStyleSheet("color: gray")
        self.sequence_name_input = QLineEdit()
        self.sequence_description_display = QTextEdit()
        self.sequence_description_display.setReadOnly(True)
        self.sequence_description_display.setPlaceholderText("Sequence description will appear here")
        self.sequence_description_display.setMaximumHeight(60)

    def _create_layout(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # --- Connection Group --- #
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(self.connect_button)
        conn_layout.addWidget(self.disconnect_button)
        conn_layout.addWidget(self.connection_status_label)
        
        # Add authentication widgets
        conn_layout.addSpacing(20)
        conn_layout.addWidget(self.user_label)
        auth_buttons_layout = QHBoxLayout()
        auth_buttons_layout.addWidget(self.login_button)
        auth_buttons_layout.addWidget(self.profile_button)
        auth_buttons_layout.addWidget(self.logout_button)
        conn_layout.addLayout(auth_buttons_layout)
        
        conn_layout.addStretch()
        conn_group.setLayout(conn_layout)

        # --- Test Context Group --- # Renamed DUT Row
        context_group = QGroupBox("Test Context")
        context_layout = QFormLayout()
        context_layout.addRow("Assemblage ID:", self.assemblage_input) # Updated Label
        # Hide operator name dropdown - will use logged in user instead
        self.operator_name_combo.setVisible(False)
        # Add operator name label to display logged-in user
        context_layout.addRow("Operator:", self.operator_name_label)
        context_layout.addRow("Sequence Name:", self.sequence_name_input)
        context_layout.addRow("Description:", self.sequence_description_display)
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

        # --- Test Sequence Group --- # Updated Layout
        seq_group = QGroupBox("Test Sequence")
        seq_main_layout = QHBoxLayout() # Main layout is now horizontal

        # Left Column (List and Buttons)
        left_v_layout = QVBoxLayout()
        left_v_layout.addWidget(QLabel("Configured Steps:"))
        left_v_layout.addWidget(self.sequence_list_widget)
        # Buttons associated with the list
        seq_list_buttons_layout = QHBoxLayout()
        seq_list_buttons_layout.addWidget(self.add_step_button)
        seq_list_buttons_layout.addWidget(self.clear_sequence_button)
        seq_list_buttons_layout.addStretch()
        left_v_layout.addLayout(seq_list_buttons_layout)

        # Right Column (Details and Run Button)
        right_v_layout = QVBoxLayout()
        right_v_layout.addWidget(QLabel("Step Details:"))
        right_v_layout.addWidget(self.step_details_output)
        # Run button associated with the whole sequence
        right_v_layout.addWidget(self.run_test_button, alignment=Qt.AlignRight)

        # Add columns to the main horizontal layout
        seq_main_layout.addLayout(left_v_layout, 1) # Give list column stretch factor 1
        seq_main_layout.addLayout(right_v_layout, 1) # Give details column stretch factor 1

        seq_group.setLayout(seq_main_layout)
        main_layout.addWidget(conn_group)
        main_layout.addWidget(context_group)
        main_layout.addWidget(cmd_group)
        main_layout.addWidget(seq_group)

        # --- Test Results Group --- #
        res_group = QGroupBox("Test Results")
        res_layout = QVBoxLayout()
        res_layout.addWidget(self.results_output)
        res_group.setLayout(res_layout)
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

        # Auth Menu
        auth_menu = menu_bar.addMenu("&Account")
        self.login_action = QAction("&Login", self)
        self.login_action.triggered.connect(self.show_login_dialog)
        self.profile_action = QAction("&Profile", self)
        self.profile_action.triggered.connect(self.show_profile_dialog)
        self.profile_action.setEnabled(False)
        self.logout_action = QAction("&Logout", self)
        self.logout_action.triggered.connect(self.logout_user)
        self.logout_action.setEnabled(False)
        
        auth_menu.addAction(self.login_action)
        auth_menu.addAction(self.profile_action)
        auth_menu.addAction(self.logout_action)

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
        # Connect the assemblage input field signal
        self.assemblage_input.editingFinished.connect(self.handle_assemblage_scan)
        # Connect sequence list selection change
        self.sequence_list_widget.currentItemChanged.connect(self.display_step_details)
        # Connect auth buttons
        self.login_button.clicked.connect(self.show_login_dialog)
        self.profile_button.clicked.connect(self.show_profile_dialog)
        self.logout_button.clicked.connect(self.logout_user)

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
                self.sequence_name_input.clear()
                self.sequence_description_display.clear()
            else:
                self.log_message("Failed to clear sequence on device.")
                self.show_error("Clear Failed", "Could not clear sequence on device. Check logs.")

    # --- Running Tests --- #

    def run_test(self):
        if not self.sequencer or not self.device or not self.device.is_open:
            self.show_error("Run Error", "Device not connected or sequencer not ready.")
            return
            
        # Check if user is authenticated
        if not self.supabase_client or not self.current_user:
            self.log_message("Authentication required: Please log in to run tests.")
            QMessageBox.warning(self, "Authentication Required", 
                              "You must be logged in to run tests and log results. Please log in first.")
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
        
        # Check if user is authenticated
        if not self.supabase_client or not self.current_user:
            self.log_message("Authentication required: Please log in to log test results.")
            QMessageBox.warning(self, "Authentication Required", 
                              "You must be logged in to log test results to the database. Please log in first.")
            return

        # Use the value from the assemblage input field
        assemblage_id_text = self.assemblage_input.text().strip() or None
        
        # Use logged-in user's name instead of operator name dropdown
        operator_name = None
        # First try to get name from profile
        if hasattr(self, 'user_profile') and self.user_profile:
            first_name = self.user_profile.get('first_name', '')
            last_name = self.user_profile.get('last_name', '')
            if first_name or last_name:
                operator_name = f"{first_name} {last_name}".strip()
        
        # If no profile name is available, use email
        if not operator_name:
            operator_name = getattr(self.current_user, 'email', None)
            
        if not operator_name:
            self.log_message("Warning: Could not determine operator name from user profile or email.")
            operator_name = "Unknown Operator"
        
        sequence_id = self.sequencer.current_sequence_id

        if sequence_id is None:
            self.log_message("Warning: No sequence ID available. Skipping Supabase log.")
            return

        self.log_message(f"Will log results with operator: {operator_name}")
        
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
                # Log the scanned/entered text as assemblage_id
                # The verification step above is for UI feedback, logging still uses the entered value.
                # If verification *must* pass before logging, add a check here.
                "assemblage_id": int(assemblage_id_text) if assemblage_id_text is not None else None,
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
            
        # Check if user is authenticated
        if not self.supabase_client or not self.current_user:
            self.log_message("Authentication required: Please log in to save sequences.")
            QMessageBox.warning(self, "Authentication Required", 
                              "You must be logged in to save sequences. Please log in first.")
            return
            
        if not self.sequencer.sequence:
            self.show_error("Save Error", "No steps in the current sequence to save.")
            return

        # Create a dialog for sequence name and description
        save_dialog = QDialog(self)
        save_dialog.setWindowTitle("Save Sequence")
        save_dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(save_dialog)
        
        # Name input
        name_layout = QFormLayout()
        name_input = QLineEdit()
        default_name = self.sequence_name_input.text().strip()
        name_input.setText(default_name)
        name_layout.addRow("Sequence Name:", name_input)
        
        # Description input
        description_input = QTextEdit()
        description_input.setPlaceholderText("Enter a description for this sequence (optional)")
        description_input.setMaximumHeight(100)
        name_layout.addRow("Description:", description_input)
        
        layout.addLayout(name_layout)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(save_dialog.accept)
        button_box.rejected.connect(save_dialog.reject)
        layout.addWidget(button_box)
        
        # Show dialog
        if save_dialog.exec():
            seq_name = name_input.text().strip()
            description = description_input.toPlainText().strip()
            
            if not seq_name:
                self.show_error("Save Failed", "Sequence name cannot be empty.")
                return
                
            self.log_message(f"Saving sequence as '{seq_name}'...")
            success, message = self.sequencer.save_sequence_to_supabase(seq_name, description)
            if success:
                self.log_message(message)
                # Update sequence name input field
                self.sequence_name_input.setText(seq_name)
                QMessageBox.information(self, "Save Successful", message)
            else:
                self.log_message(f"Save failed: {message}")
                self.show_error("Save Failed", message)
        else:
            self.log_message("Save cancelled by user.")

    def load_sequence(self):
        if not self.sequencer or not self.device or not self.device.is_open:
             self.show_error("Load Error", "Device must be connected to load.")
             return
             
        # Check if user is authenticated
        if not self.supabase_client or not self.current_user:
            self.log_message("Authentication required: Please log in to load sequences.")
            QMessageBox.warning(self, "Authentication Required", 
                              "You must be logged in to load sequences. Please log in first.")
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
                    # Update sequence name and description fields 
                    if self.sequencer.current_sequence_name:
                        self.sequence_name_input.setText(self.sequencer.current_sequence_name)
                    else: # Fallback if name wasn't stored somehow
                        for name, sid, _ in saved_sequences:
                             if sid == sequence_id:
                                  self.sequence_name_input.setText(name)
                                  break
                                  
                    # Display sequence description if available
                    if self.sequencer.current_sequence_description:
                        description_msg = f"Sequence Description: {self.sequencer.current_sequence_description}"
                        self.log_message(description_msg)
                        self.sequence_description_display.setText(self.sequencer.current_sequence_description)
                    else:
                        self.sequence_description_display.clear()
                else:
                    self.show_error("Load Failed", "Could not load sequence details from Supabase.")
                    self.sequence_description_display.clear()
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

    # --- Assemblage Handling --- #
    @Slot()
    def handle_assemblage_scan(self):
        """Called when the user finishes editing the Assemblage ID field (e.g., after scan)."""
        scanned_id_str = self.assemblage_input.text().strip()
        if not scanned_id_str:
            # Field cleared, maybe clear related info?
            return

        self.log_message(f"Assemblage ID scanned/entered: {scanned_id_str}")

        if not self.supabase_client or not self.current_user:
            self.log_message("Authentication required: Please log in to verify Assemblage ID.")
            QMessageBox.warning(self, "Authentication Required", 
                              "You must be logged in to verify Assemblage IDs. Please log in first.")
            return

        try:
            # Assume the barcode contains the integer ID
            assemblage_id = int(scanned_id_str)
        except ValueError:
            self.log_message(f"Error: Scanned Assemblage ID '{scanned_id_str}' is not a valid integer.")
            # Optionally clear the field or show a visual warning
            # self.assemblage_input.setStyleSheet("border: 1px solid red;") # Example
            QMessageBox.warning(self, "Invalid ID", f"The scanned Assemblage ID '{scanned_id_str}' is not a valid number.")
            return

        # Query Supabase to verify the ID exists
        try:
            self.log_message(f"Verifying Assemblage ID {assemblage_id} in Supabase...")
            response = self.supabase_client.table("assemblages") \
                                           .select("id, assemblage_name") \
                                           .eq("id", assemblage_id) \
                                           .maybe_single() \
                                           .execute()

            if response.data:
                assemblage_name = response.data.get('assemblage_name', '(No Name)')
                self.log_message(f"Assemblage ID {assemblage_id} verified. Name: '{assemblage_name}'")
                # Clear any visual warning
                # self.assemblage_input.setStyleSheet("") # Reset style
                # Optionally update other UI elements if needed
            else:
                self.log_message(f"Error: Assemblage ID {assemblage_id} not found in Supabase.")
                # Optionally clear the field or show a visual warning
                # self.assemblage_input.setStyleSheet("border: 1px solid red;")
                QMessageBox.warning(self, "ID Not Found", f"Assemblage ID {assemblage_id} was not found in the database.")

        except Exception as e:
            self.log_message(f"Error querying Supabase for Assemblage ID: {e}")
            self.show_error("Supabase Error", f"Could not verify Assemblage ID: {e}")

    # --- Display Step Details --- #
    @Slot(QListWidgetItem, QListWidgetItem)
    def display_step_details(self, current_item, previous_item):
        """Displays the parameters of the selected step in the details view."""
        self.step_details_output.clear()
        if not current_item or not self.sequencer:
            return

        # Get the index stored in the item
        step_index = current_item.data(Qt.UserRole)
        if step_index is None or step_index >= len(self.sequencer.sequence):
            self.step_details_output.setText("Error: Could not retrieve step data.")
            return

        step_config = self.sequencer.sequence[step_index]

        # Format and display the details
        details_text = f"<b>Step {step_index + 1}: {step_config.get('type', 'Unknown')}</b><br>"
        if step_config.get('step_name'):
            details_text += f"Name: {step_config['step_name']}<br>"
        details_text += "<br><b>Parameters:</b><br>"

        # Display parameters nicely
        for key, value in step_config.items():
            if key not in ['type', 'step_name']: # Skip keys already displayed
                 # Simple formatting, could improve (e.g., units)
                 key_display = key.replace('_', ' ').title()
                 value_display = str(value)
                 # Handle boolean for checkbox params
                 if isinstance(value, bool):
                     value_display = "Yes" if value else "No"
                 # Handle empty strings
                 if value_display == "":
                     value_display = "<i>(Not set)</i>"
                 details_text += f"&nbsp;&nbsp;{key_display:<18}: {value_display}<br>"

        self.step_details_output.setText(details_text)

    # --- Authentication Handling --- #
    
    def show_profile_dialog(self):
        """Show the profile dialog for viewing and editing user profile"""
        if not self.supabase_client or not self.current_user:
            self.show_error("Profile Error", "You must be logged in to view your profile.")
            return
            
        dialog = ProfileDialog(self.supabase_client, self.current_user, self)
        dialog.profile_updated.connect(self._handle_profile_updated)
        
        if dialog.exec():
            self.log_message("Profile updated successfully.")
        else:
            self.log_message("Profile dialog closed.")
    
    def _handle_profile_updated(self):
        """Handle when profile has been updated in the profile dialog"""
        self._update_auth_ui()  # Refresh UI with new profile info
    
    def show_login_dialog(self):
        """Show the login dialog and handle authentication"""
        if not self.supabase_client:
            self.show_error("Authentication Error", "Supabase client not available.")
            return
            
        dialog = LoginDialog(self.supabase_client, self)
        dialog.login_successful.connect(self.handle_login_success)
        
        if dialog.exec():
            # Dialog accepted (login successful)
            pass
        else:
            # Dialog rejected or closed
            self.log_message("Login cancelled.")
    
    def handle_login_success(self, user_data):
        """Handle successful login"""
        self.current_user = user_data
        # Access user email as an attribute instead of dictionary lookup
        user_email = getattr(self.current_user, 'email', 'Unknown')
        self.log_message(f"Logged in as {user_email}")
        
        # Save the session for future use
        if self.supabase_client and hasattr(self.supabase_client.auth, 'get_session'):
            try:
                session = self.supabase_client.auth.get_session()
                save_session(session)
            except Exception as e:
                self.log_message(f"Could not save session: {e}")
        
        # Fetch profile information
        if self.supabase_client:
            try:
                # Access user ID as an attribute
                user_id = getattr(self.current_user, 'id', None)
                if user_id:
                    response = self.supabase_client.table("profiles") \
                        .select("first_name, last_name, phone_number") \
                        .eq("id", user_id) \
                        .maybe_single() \
                        .execute()
                    
                    if response.data:
                        # Store profile info separately since it's a dictionary
                        self.user_profile = response.data
                        self.log_message(f"Loaded profile for {self.user_profile.get('first_name', '')} {self.user_profile.get('last_name', '')}")
                    else:
                        self.log_message("No profile information found for user")
                        self.user_profile = {}
            except Exception as e:
                self.log_message(f"Error fetching profile: {e}")
                self.user_profile = {}
        
        self._update_auth_ui()

    def logout_user(self):
        """Sign out the current user"""
        if not self.supabase_client:
            return
            
        try:
            self.supabase_client.auth.sign_out()
            self.current_user = None
            self.log_message("Logged out successfully")
            
            # Clear the saved session
            clear_session()
            
            self._update_auth_ui()
        except Exception as e:
            self.log_message(f"Error during logout: {e}")
    
    def _update_auth_ui(self):
        """Update the UI based on authentication state"""
        is_logged_in = self.current_user is not None
        
        # Update buttons
        self.login_button.setVisible(not is_logged_in)
        self.profile_button.setVisible(is_logged_in)
        self.profile_button.setEnabled(is_logged_in)
        self.logout_button.setVisible(is_logged_in)
        self.login_action.setEnabled(not is_logged_in)
        self.profile_action.setEnabled(is_logged_in)
        self.logout_action.setEnabled(is_logged_in)
        
        # Update user display
        if is_logged_in:
            # Access email as an attribute
            email = getattr(self.current_user, 'email', 'Unknown')
            # Get user's name from profile if available
            if hasattr(self, 'user_profile') and self.user_profile:
                first_name = self.user_profile.get('first_name', '')
                last_name = self.user_profile.get('last_name', '')
                
                if first_name or last_name:
                    display_name = f"{first_name} {last_name}".strip()
                    self.user_label.setText(f"Logged in as: {display_name}")
                    self.operator_name_label.setText(f"Operator: {display_name}")
                else:
                    self.user_label.setText(f"Logged in as: {email}")
                    self.operator_name_label.setText(f"Operator: {email}")
            else:
                self.user_label.setText(f"Logged in as: {email}")
                self.operator_name_label.setText(f"Operator: {email}")
                
            self.user_label.setStyleSheet("color: green")
            self.operator_name_label.setStyleSheet("color: green")
        else:
            self.user_label.setText("Not logged in")
            self.user_label.setStyleSheet("color: gray")
            self.operator_name_label.setText("Operator: Not logged in")
            self.operator_name_label.setStyleSheet("color: gray")
            
        # Update UI elements based on login state
        # Only enable database-dependent operations if logged in
        if self.device and self.device.is_open:
            # Only update these if the device is connected, otherwise they're disabled anyway
            save_enabled = is_logged_in and len(self.sequencer.sequence) > 0 if self.sequencer else False
            self.add_step_button.setEnabled(True)  # Adding steps doesn't require login
            self.run_test_button.setEnabled(is_logged_in)  # Running tests requires login for logging results
            
            # Update menu actions
            for action in self.menuBar().actions():
                if action.text() == "&File":
                    file_menu = action.menu()
                    for file_action in file_menu.actions():
                        if file_action.text() == "&Save Sequence...":
                            file_action.setEnabled(save_enabled)
                        elif file_action.text() == "&Load Sequence...":
                            file_action.setEnabled(is_logged_in)

if __name__ == '__main__':
    # This check is important for multiprocessing/QThread safety on some platforms
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 
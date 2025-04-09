from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPushButton, QDialogButtonBox, QCheckBox, QLabel, QWidget
)
from PySide6.QtCore import Slot

# Assuming utils package is in the python path or relative import works
from utils.constants import TEST_TYPES
from utils.parsing import parse_current_input # For validation/parsing if needed here

class TestSetupDialog(QDialog):
    def __init__(self, test_type_keys, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Test Step")
        self.test_type_keys = test_type_keys
        self.current_test_type = None
        self.param_widgets = {} # Store dynamically created widgets

        # Main Layout
        layout = QVBoxLayout(self)

        # -- Step Name -- #
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Step Name (Optional):"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., ACW Phase A")
        self.param_widgets['step_name'] = self.name_input # Add to widgets dict
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # -- Test Type Selection -- #
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Test Type:"))
        self.type_combo = QComboBox()
        # Use the descriptive names from TEST_TYPES for display
        for key in self.test_type_keys:
            self.type_combo.addItem(TEST_TYPES.get(key, key), key) # Display name, store key
        self.type_combo.currentIndexChanged.connect(self.update_parameter_fields)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)

        # Parameter Form Area (Dynamically populated)
        self.param_form_layout = QFormLayout()
        self.param_form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        param_widget = QWidget()
        param_widget.setLayout(self.param_form_layout)
        layout.addWidget(param_widget)

        # Dialog Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        # Initialize with the first test type
        if self.test_type_keys:
            self.update_parameter_fields(0)

    @Slot(int)
    def update_parameter_fields(self, index):
        # Clear existing parameter widgets
        while self.param_form_layout.rowCount() > 0:
            self.param_form_layout.removeRow(0)
        self.param_widgets.clear()

        # Get the selected test type key (like "ACW")
        self.current_test_type = self.type_combo.itemData(index)
        if not self.current_test_type:
            return

        # Define parameters for each test type
        # Structure: { 'param_name': {'label': 'Label Text', 'default': 'DefaultValue', 'type': 'QLineEdit'/'QCheckBox'/'QComboBox', 'tooltip': 'Optional help'} }
        params_definition = {}
        if self.current_test_type == "ACW":
            params_definition = {
                'voltage': {'label': 'Voltage (V)', 'default': '1000', 'tooltip': '50-5000 V'},
                'ramp_time': {'label': 'Ramp Time (s)', 'default': '1.0', 'tooltip': '0.1-999 s'},
                'dwell_time': {'label': 'Dwell Time (s)', 'default': '2.0', 'tooltip': '0.2-999 s'},
                'min_limit': {'label': 'Min Current Limit', 'default': '', 'tooltip': 'e.g., 1uA, 0.5mA (blank=none)'},
                'max_limit': {'label': 'Max Current Limit', 'default': '5mA', 'tooltip': 'e.g., 20mA, 0.01A (0.001-100A range)'},
                'ground_check': {'label': 'Ground Check', 'default': False, 'type': 'QCheckBox'}
            }
        elif self.current_test_type == "DCW":
             params_definition = {
                'voltage': {'label': 'Voltage (V)', 'default': '1000', 'tooltip': '50-6000 V'},
                'ramp_time': {'label': 'Ramp Time (s)', 'default': '1.0', 'tooltip': '0.1-999 s'},
                'dwell_time': {'label': 'Dwell Time (s)', 'default': '2.0', 'tooltip': '0.2-999 s'},
                'min_limit': {'label': 'Min Current Limit', 'default': '', 'tooltip': 'e.g., 1uA (blank=none)'},
                'max_limit': {'label': 'Max Current Limit', 'default': '5mA', 'tooltip': 'e.g., 5mA, 500uA (1uA-20mA range)'},
                'ground_check': {'label': 'Ground Check', 'default': False, 'type': 'QCheckBox'}
            }
        elif self.current_test_type == "IR":
            params_definition = {
                'voltage': {'label': 'Voltage (V)', 'default': '500', 'tooltip': '50-6000 V'},
                'ramp_time': {'label': 'Ramp Time (s)', 'default': '1.0', 'tooltip': '0.1-999 s'},
                'dwell_time': {'label': 'Dwell Time (s)', 'default': '2.0', 'tooltip': '0.2-999 s'},
                'min_limit': {'label': 'Min Resistance (Ω)', 'default': '', 'tooltip': 'e.g., 1M, 500k (blank=none)'},
                'max_limit': {'label': 'Max Resistance (Ω)', 'default': '', 'tooltip': 'e.g., 10G (blank=none)'}
            }
        elif self.current_test_type == "CONT":
            params_definition = {
                'current': {'label': 'Test Current (A)', 'default': '0.1', 'tooltip': '0.01-30 A'},
                'min_limit': {'label': 'Min Resistance (Ω)', 'default': '', 'tooltip': 'blank=none'},
                'max_limit': {'label': 'Max Resistance (Ω)', 'default': '0.1', 'tooltip': 'Recommended < 1Ω'},
                'dwell_time': {'label': 'Dwell Time (s)', 'default': '1.0', 'tooltip': '0.2-999 s'}
            }
        elif self.current_test_type == "GND":
            params_definition = {
                'current': {'label': 'Test Current (A)', 'default': '10', 'tooltip': '1-30 A'},
                'max_limit': {'label': 'Max Resistance (Ω)', 'default': '0.1', 'tooltip': '0.001-1 Ω'},
                'dwell_time': {'label': 'Dwell Time (s)', 'default': '2.0', 'tooltip': '0.2-999 s'},
                'freq': {'label': 'Frequency (Hz)', 'default': '60', 'type': 'QComboBox', 'options': ['50', '60']}
            }

        # Create and add widgets for the selected type
        for name, config in params_definition.items():
            label_text = config.get('label', name.replace('_', ' ').title())
            default_val = config.get('default')
            widget_type = config.get('type', 'QLineEdit')
            tooltip = config.get('tooltip', '')

            widget = None
            if widget_type == 'QLineEdit':
                widget = QLineEdit()
                if default_val is not None:
                    widget.setText(str(default_val))
                widget.setPlaceholderText(tooltip) # Use tooltip as placeholder
            elif widget_type == 'QCheckBox':
                widget = QCheckBox()
                if default_val:
                    widget.setChecked(True)
            elif widget_type == 'QComboBox':
                widget = QComboBox()
                options = config.get('options', [])
                widget.addItems(options)
                if default_val in options:
                    widget.setCurrentText(default_val)

            if widget:
                widget.setToolTip(tooltip)
                self.param_widgets[name] = widget
                self.param_form_layout.addRow(label_text + ":", widget)

    def get_step_config(self):
        """Retrieve the configuration dictionary from the UI widgets."""
        if not self.current_test_type:
            return None

        config = {
            'type': self.current_test_type,
            'step_name': self.name_input.text().strip() # Get step name
        }
        # Retrieve other dynamic parameters
        for name, widget in self.param_widgets.items():
            if name == 'step_name': continue # Already handled

            if isinstance(widget, QLineEdit):
                config[name] = widget.text().strip()
            elif isinstance(widget, QCheckBox):
                config[name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                config[name] = widget.currentText()
            # Add other widget types if needed

        # Optional: Add validation here before returning
        # e.g., check if required fields are filled, use parse_current_input
        if self.current_test_type in ["ACW", "DCW"]:
            min_limit = parse_current_input(config.get('min_limit', ""))
            max_limit = parse_current_input(config.get('max_limit', ""))
            if min_limit is None or max_limit is None:
                 # You might want to show an error in the dialog instead of just returning None
                 print("Error: Invalid current format in limits.")
                 # Consider using QMessageBox.warning(self, "Input Error", "Invalid current format...")
                 return None
            # Store raw input or parsed? Storing raw might be simpler for resending
            # config['min_limit_parsed'] = min_limit
            # config['max_limit_parsed'] = max_limit

        return config

# Example Usage (for testing the dialog standalone)
if __name__ == '__main__':
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    test_types_available = list(TEST_TYPES.keys())
    dialog = TestSetupDialog(test_types_available)
    if dialog.exec():
        print("Dialog Accepted. Configuration:")
        config = dialog.get_step_config()
        print(config)
    else:
        print("Dialog Cancelled.")
    sys.exit() 
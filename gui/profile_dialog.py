from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QMessageBox, QFormLayout, QDialogButtonBox
)
from PySide6.QtCore import Signal

class ProfileDialog(QDialog):
    profile_updated = Signal()  # Signal to emit when profile is updated
    
    def __init__(self, supabase_client, user_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Profile")
        self.setMinimumWidth(400)
        self.supabase_client = supabase_client
        self.user_data = user_data
        
        # Get profile data from parent window if available
        parent_window = parent
        if parent_window and hasattr(parent_window, 'user_profile'):
            self.profile_data = parent_window.user_profile
        else:
            self.profile_data = {}
        
        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._populate_fields()
    
    def _create_widgets(self):
        self.email_label = QLabel()
        
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText("Enter your first name")
        
        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText("Enter your last name")
        
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Enter your phone number")
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red")
    
    def _create_layout(self):
        layout = QVBoxLayout(self)
        
        # Email is read-only from auth
        email_layout = QHBoxLayout()
        email_layout.addWidget(QLabel("Email:"))
        email_layout.addWidget(self.email_label)
        layout.addLayout(email_layout)
        
        form_layout = QFormLayout()
        form_layout.addRow("First Name:", self.first_name_input)
        form_layout.addRow("Last Name:", self.last_name_input)
        form_layout.addRow("Phone:", self.phone_input)
        layout.addLayout(form_layout)
        
        layout.addWidget(self.button_box)
        layout.addWidget(self.status_label)
    
    def _connect_signals(self):
        self.button_box.accepted.connect(self.save_profile)
        self.button_box.rejected.connect(self.reject)
    
    def _populate_fields(self):
        # Set the email from auth - access as attribute
        self.email_label.setText(getattr(self.user_data, 'email', 'Unknown'))
        
        # Set profile fields
        self.first_name_input.setText(self.profile_data.get('first_name', ''))
        self.last_name_input.setText(self.profile_data.get('last_name', ''))
        self.phone_input.setText(self.profile_data.get('phone_number', ''))
    
    def save_profile(self):
        # Save profile data to Supabase
        try:
            self.status_label.setText("Saving profile...")
            
            # Get values from inputs
            first_name = self.first_name_input.text().strip()
            last_name = self.last_name_input.text().strip()
            phone_number = self.phone_input.text().strip()
            
            # Prepare update data
            update_data = {
                "first_name": first_name,
                "last_name": last_name,
                "phone_number": phone_number
            }
            
            # Save to Supabase - access ID as attribute
            user_id = getattr(self.user_data, 'id', None)
            if not user_id:
                self.status_label.setText("Error: User ID not available")
                return
                
            response = self.supabase_client.table("profiles")\
                .upsert({"id": user_id, **update_data})\
                .execute()
                
            if response.data:
                # Update parent window profile data
                parent_window = self.parent()
                if parent_window:
                    parent_window.user_profile = update_data
                
                self.profile_updated.emit()
                QMessageBox.information(self, "Success", "Profile updated successfully")
                self.accept()
            else:
                self.status_label.setText("Error saving profile")
                
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}") 
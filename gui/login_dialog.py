from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QMessageBox, QCheckBox, QFormLayout
)
from PySide6.QtCore import Signal
from utils.supabase_client import save_session
import logging

class LoginDialog(QDialog):
    login_successful = Signal(object)  # Signal to emit user data when login succeeds
    
    def __init__(self, supabase_client, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")
        self.setMinimumWidth(350)
        self.supabase_client = supabase_client
        self.user_data = None
        self.session = None
        
        # Set up a logger for this dialog
        self.logger = logging.getLogger('hipot.login')
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        self.logger.propagate = False  # Prevent double logging or swallowing by parent loggers
        
        self._create_widgets()
        self._create_layout()
        self._connect_signals()
    
    def _create_widgets(self):
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter your email")
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.remember_checkbox = QCheckBox("Remember me")
        
        self.login_button = QPushButton("Login")
        self.cancel_button = QPushButton("Cancel")
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red")
    
    def _create_layout(self):
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        form_layout.addRow("Email:", self.email_input)
        form_layout.addRow("Password:", self.password_input)
        layout.addLayout(form_layout)
        
        layout.addWidget(self.remember_checkbox)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        layout.addWidget(self.status_label)
    
    def _connect_signals(self):
        self.login_button.clicked.connect(self.attempt_login)
        self.cancel_button.clicked.connect(self.reject)
        self.email_input.returnPressed.connect(self.attempt_login)
        self.password_input.returnPressed.connect(self.attempt_login)
    
    def attempt_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text()
        masked_password = '*' * len(password) if password else ''
        self.logger.debug(f"Attempting login with email: {email}, password: {masked_password}")
        
        if not email or not password:
            self.logger.warning("Login attempt with missing email or password.")
            self.status_label.setText("Please enter both email and password")
            return
        
        try:
            self.status_label.setText("Signing in...")
            self.login_button.setEnabled(False)
            self.logger.info(f"Signing in user: {email}")
            
            # Try to sign in with Supabase
            response = self.supabase_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            self.logger.info(f"Sign-in response: {response}")
            
            # Store the session
            self.session = response.session
            self.logger.debug(f"Session received: {self.session}")
            
            # Save session now if "Remember Me" is checked
            if self.remember_checkbox.isChecked() and self.session:
                self.logger.info("'Remember me' checked. Saving session.")
                save_session(self.session)
            
            # Login successful
            self.user_data = response.user
            self.logger.info(f"Login successful for user: {getattr(self.user_data, 'email', 'Unknown')}")
            self.login_successful.emit(response.user)
            self.accept()
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Login error for user {email}: {error_msg}")
            if "Invalid login credentials" in error_msg:
                self.status_label.setText("Invalid email or password")
            else:
                self.status_label.setText(f"Login error: {error_msg}")
            self.login_button.setEnabled(True)
    
    def get_user_data(self):
        return self.user_data
    
    def get_session(self):
        return self.session 
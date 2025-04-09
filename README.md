# Hipot Test Automation GUI

## Description

This application provides a graphical user interface (GUI) for controlling a V7x series electrical safety tester (hipot tester). It allows users to load test sequences from a Supabase database, program them onto the device, run tests, and view results.

## Features

- Connect to and communicate with a V7x hipot tester via USB.
- Load predefined test sequences from a Supabase cloud database.
- Program the test sequence onto the V7x device automatically upon loading.
- Initiate and monitor the execution of test sequences.
- User-friendly interface built with PySide6.

## Prerequisites

- Python 3.x
- A V7x series hipot tester.
- Necessary drivers for the V7x tester and the Silicon Labs USB-to-UART bridge (likely included via `SLABHIDtoUART.dll` and `SLABHIDDevice.dll`). Ensure these are correctly installed or placed for the application to find them.
- Access to a Supabase project for storing/retrieving test sequences.

## Installation

1.  **Clone the repository:**

    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```

2.  **Create a virtual environment (recommended):**

    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Create a `.env` file:** Create a file named `.env` in the root directory of the project.
2.  **Add Supabase Credentials:** Copy the contents of `.env.example` (if available) or add the following lines to your `.env` file, replacing the placeholder values with your actual Supabase project URL and anon key:

    ```dotenv
    # Supabase Secrets - Replace placeholders with your actual credentials
    # Find these in your Supabase project settings: Project Settings > API

    # Your Supabase Project URL
    SUPABASE_URL=YOUR_SUPABASE_URL

    # Your Supabase Anon Key
    SUPABASE_KEY=YOUR_SUPABASE_ANON_KEY
    ```

    _Note: Use the `anon` key as this application runs client-side._

## Usage

1.  Ensure the V7x tester is connected to the computer via USB.
2.  Make sure the required DLLs (`SLABHIDtoUART.dll`, `SLABHIDDevice.dll`) are accessible by the application (e.g., in the same directory as `main.py` or in the system's PATH).
3.  Run the application from the project's root directory:
    ```bash
    python main.py
    ```
4.  Use the GUI to connect to the device, load a test sequence from Supabase (which will automatically program it), and run the test.

## Dependencies

- PySide6 (`>=6.0.0`): For the graphical user interface.
- Supabase Client (`>=2.0.0`): For interacting with the Supabase database.
- python-dotenv (`>=1.0.0`): For loading environment variables from the `.env` file.
- Silicon Labs HID to UART Library (`SLABHIDtoUART.dll`, `SLABHIDDevice.dll`): Required for USB communication with the device.

## Project Structure

```
.
├── .env                # Environment variables (Supabase credentials) - **DO NOT COMMIT**
├── .gitignore          # Specifies intentionally untracked files that Git should ignore
├── README.md           # This file
├── requirements.txt    # Python package dependencies
├── SLABCP2110.h        # Header file for Silicon Labs library (likely)
├── SLABHIDDevice.dll   # Silicon Labs HID device library
├── SLABHIDtoUART.dll   # Silicon Labs HID to UART bridge library
├── SLABHIDtoUART.lib   # Silicon Labs HID to UART import library
├── device/             # Modules related to device communication (e.g., V7x commands)
├── gui/                # Modules related to the graphical user interface (PySide6)
│   └── main_window.py  # Main application window logic
├── hipot_cmd.py        # Core logic for communicating with the Hipot tester (likely)
├── main.py             # Main application entry point
├── testing/            # Test files or modules (if any)
└── utils/              # Utility functions or modules
```

_(Feel free to add sections like Contributing, License, etc. as needed)_

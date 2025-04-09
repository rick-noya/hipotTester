import re

def parse_current_input(input_str, default_unit='A'):
    """
    Parses a current string (e.g., "10mA", "50uA", "0.01A", "15")
    and returns the value in Amps as a string suitable for SCPI.
    Returns None if parsing fails, empty string if input is blank.
    """
    if not input_str:
        return "" # Return empty string if input is blank (often allowed for limits)

    input_str = input_str.strip()
    # Regular expression to capture value and optional unit (mA, uA, A)
    # Allows for floating point numbers, scientific notation (e.g., 1.5e-3)
    match = re.match(r"^(-?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([mu]?[aA]?)?$", input_str, re.IGNORECASE)

    if not match:
        # print(f"Error: Invalid current format '{input_str}'. Use numbers like 10mA, 50uA, 0.01A, or 15.")
        return None # Indicate parsing error

    value_str, unit = match.groups()
    try:
        value = float(value_str)
    except ValueError:
        # print(f"Error: Could not convert value '{value_str}' to a number.")
        return None # Indicate conversion error

    unit = unit.lower() if unit else default_unit.lower() # Default to Amps if no unit

    if unit == 'ma':
        value /= 1000.0
    elif unit == 'ua':
        value /= 1000000.0
    elif unit == 'a' or not unit: # Handle 'A' or no unit as Amps
        pass # Value is already in Amps
    else:
        # print(f"Error: Unknown current unit '{unit}' in '{input_str}'. Use mA, uA, or A.")
        return None # Indicate parsing error

    # Return as string, formatted to avoid excessive precision issues for SCPI
    # Using general format 'g' which avoids trailing zeros and switches to scientific if needed
    return f"{value:g}"

# TODO: Implement parse_resistance_input similar to parse_current_input
# def parse_resistance_input(input_str, default_unit='Ω'):
#     # ... parsing logic for kΩ, MΩ, GΩ ...
#     pass 
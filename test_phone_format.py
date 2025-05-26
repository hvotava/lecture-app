#!/usr/bin/env python3
"""
Test formátování telefonního čísla
"""
import re

def format_phone_number_e164(phone: str) -> str:
    """Formátuje telefonní číslo do čistého E.164 formátu pro Twilio volání."""
    # Odstraň všechny nečíselné znaky
    digits = re.sub(r'[^\d+]', '', phone)
    
    # Pokud číslo začíná 00, nahraď to za +420
    if digits.startswith('00'):
        digits = '+420' + digits[2:]
    
    # Pokud číslo začíná 0, nahraď to za +420
    elif digits.startswith('0'):
        digits = '+420' + digits[1:]
    
    # Pokud číslo nezačíná +, přidej +420
    elif not digits.startswith('+'):
        digits = '+420' + digits
    
    # Odstraň duplicitní +420
    if digits.startswith('+420420'):
        digits = '+420' + digits[7:]
    
    return digits

# Test s různými formáty
test_numbers = [
    "+420 724 369 467",
    "+420724369467",
    "724369467",
    "0724369467",
    "00420724369467"
]

print("Test formátování telefonních čísel:")
print("=" * 50)

for number in test_numbers:
    formatted = format_phone_number_e164(number)
    print(f"Vstup: '{number}' -> Výstup: '{formatted}'")

print("\nOčekávaný výstup pro všechny: '+420724369467'") 
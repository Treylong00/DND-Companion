import re
import json
import os
from datetime import datetime
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import io


def extract_data_from_image(image):
    """
    Extract character data from a character sheet image using OCR

    Args:
        image: PIL Image object of the character sheet

    Returns:
        Dictionary containing character data extracted from the image
    """
    # Extract text from image using OCR
    text = pytesseract.image_to_string(image)

    # Initialize character data
    character_data = {
        "id": datetime.now().strftime('%Y%m%d%H%M%S'),
        "name": "",
        "race": "",
        "class": "",
        "level": 1,
        "abilities": {
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10
        },
        "hp": {
            "max": 10,
            "current": 10
        },
        "armor_class": 10,
        "proficiency_bonus": 2,
        "skills": [],
        "equipment": [],
        "spells": [],
        "background": "",
        "traits": ""
    }

    # Extract character name
    name_match = re.search(r'CHARACTER NAME\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if name_match:
        character_data["name"] = name_match.group(1).strip()

    # Extract race
    race_match = re.search(r'RACE\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if race_match:
        character_data["race"] = race_match.group(1).strip()

    # Extract class and level
    class_level_match = re.search(r'CLASS & LEVEL\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if class_level_match:
        class_level = class_level_match.group(1).strip()
        # Try to separate class and level
        level_match = re.search(r'(\d+)', class_level)
        if level_match:
            character_data["level"] = int(level_match.group(1))
            character_data["class"] = class_level.replace(level_match.group(0), '').strip()
        else:
            character_data["class"] = class_level

    # Extract ability scores
    ability_scores = {
        "strength": re.search(r'STRENGTH\s*(\d+)', text, re.IGNORECASE),
        "dexterity": re.search(r'DEXTERITY\s*(\d+)', text, re.IGNORECASE),
        "constitution": re.search(r'CONSTITUTION\s*(\d+)', text, re.IGNORECASE),
        "intelligence": re.search(r'INTELLIGENCE\s*(\d+)', text, re.IGNORECASE),
        "wisdom": re.search(r'WISDOM\s*(\d+)', text, re.IGNORECASE),
        "charisma": re.search(r'CHARISMA\s*(\d+)', text, re.IGNORECASE)
    }

    for ability, match in ability_scores.items():
        if match:
            character_data["abilities"][ability] = int(match.group(1))

    # Extract HP
    hp_max_match = re.search(r'Hit Point Maximum\s*(\d+)', text, re.IGNORECASE)
    if hp_max_match:
        character_data["hp"]["max"] = int(hp_max_match.group(1))

    current_hp_match = re.search(r'CURRENT HIT POINTS\s*(\d+)', text, re.IGNORECASE)
    if current_hp_match:
        character_data["hp"]["current"] = int(current_hp_match.group(1))

    # Extract armor class
    ac_match = re.search(r'ARMOR\s*CLASS\s*(\d+)', text, re.IGNORECASE)
    if ac_match:
        character_data["armor_class"] = int(ac_match.group(1))

    # Extract proficiency bonus
    prof_bonus_match = re.search(r'PROFICIENCY BONUS\s*\+(\d+)', text, re.IGNORECASE)
    if prof_bonus_match:
        character_data["proficiency_bonus"] = int(prof_bonus_match.group(1))

    # Extract skills (simplified approach)
    skills = ["Acrobatics", "Animal Handling", "Arcana", "Athletics", "Deception", "History",
              "Insight", "Intimidation", "Investigation", "Medicine", "Nature", "Perception",
              "Performance", "Persuasion", "Religion", "Sleight of Hand", "Stealth", "Survival"]

    for skill in skills:
        if re.search(rf'{skill}\s*[\(\w+\)]*\s*[✓✗●○☑☐]', text, re.IGNORECASE):
            character_data["skills"].append(skill)

    # Extract equipment
    equipment_section = re.search(r'EQUIPMENT(.*?)(?:FEATURES|ATTACKS|\Z)', text, re.DOTALL | re.IGNORECASE)
    if equipment_section:
        equipment_text = equipment_section.group(1).strip()
        equipment_items = [item.strip() for item in equipment_text.split('\n') if item.strip()]
        character_data["equipment"] = equipment_items

    # Extract features and traits
    traits_section = re.search(r'FEATURES & TRAITS(.*?)(?:\Z)', text, re.DOTALL | re.IGNORECASE)
    if traits_section:
        character_data["traits"] = traits_section.group(1).strip()

    # Extract backstory
    backstory_section = re.search(r'CHARACTER BACKSTORY(.*?)(?:TREASURE|\Z)', text, re.DOTALL | re.IGNORECASE)
    if backstory_section:
        character_data["background"] = backstory_section.group(1).strip()

    return character_data


def import_character_from_scanned_pdf(pdf_file, save_dir):
    """
    Process a scanned character sheet PDF using OCR and save it to the data directory

    Args:
        pdf_file: File path of the uploaded PDF
        save_dir: Directory to save the processed character data

    Returns:
        tuple: (character_id, error_message)
    """
    try:
        # Convert PDF to images
        images = convert_from_path(pdf_file)

        # Extract data from the first page (main character sheet)
        character_data = extract_data_from_image(images[0])

        # If there's no name, use a default
        if not character_data.get("name"):
            character_data["name"] = "Imported Character"

        # Save the character data
        character_id = character_data["id"]
        file_path = os.path.join(save_dir, f"{character_id}.json")

        with open(file_path, 'w') as file:
            json.dump(character_data, file, indent=2)

        return character_id, None
    except Exception as e:
        return None, f"Error processing PDF with OCR: {str(e)}"


# This is a fallback function if PyPDF2 can't find form fields
def try_import_methods(pdf_file, save_dir):
    """Try different import methods for the PDF"""
    try:
        # First try form fields with PyPDF2
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_file)
        fields = reader.get_form_text_fields()

        if fields and len(fields) > 3:  # If we have a reasonable number of form fields
            from pdf_import import import_character_from_pdf
            return import_character_from_pdf(pdf_file, save_dir)
        else:
            # Fall back to OCR
            return import_character_from_scanned_pdf(pdf_file, save_dir)
    except Exception as e:
        # If all else fails, try OCR
        return import_character_from_scanned_pdf(pdf_file, save_dir)
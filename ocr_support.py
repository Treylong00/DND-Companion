import os
import json
from datetime import datetime
import pdf2image
import pytesseract
import cv2
import numpy as np
import re


def import_character_from_scanned_pdf(pdf_path, data_dir):
    """
    Import a D&D character from a scanned (non-fillable) PDF using OCR.

    Args:
        pdf_path (str): Path to the PDF file
        data_dir (str): Directory to save the character data

    Returns:
        tuple: (character_id, error_message)
    """
    try:
        # Convert PDF to images
        images = pdf2image.convert_from_path(pdf_path)

        # Extract text from all pages
        full_text = ""
        for i, img in enumerate(images):
            # Convert PIL image to OpenCV format
            open_cv_image = np.array(img)
            open_cv_image = open_cv_image[:, :, ::-1].copy()

            # Preprocess image for better OCR
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)

            # Apply threshold to enhance text
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

            # Apply noise reduction
            denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)

            # Apply OCR with custom configuration for better accuracy
            config = r'--oem 3 --psm 6'
            page_text = pytesseract.image_to_string(denoised, config=config)

            # Debug: save OCR text for each page
            # with open(f"ocr_page_{i}.txt", "w") as f:
            #     f.write(page_text)

            full_text += page_text + "\n"

        # Extract character data from OCR text
        character_data = extract_character_data_from_text(full_text)

        # Save the character data
        character_path = os.path.join(data_dir, f"{character_data['id']}.json")
        with open(character_path, 'w') as outfile:
            json.dump(character_data, outfile, indent=2)

        return character_data['id'], None

    except Exception as e:
        return None, f"OCR error: {str(e)}"


def extract_character_data_from_text(text):
    """
    Extract character data from OCR text.

    Args:
        text (str): OCR extracted text

    Returns:
        dict: Character data
    """
    # Generate a unique ID for the character
    character_id = datetime.now().strftime('%Y%m%d%H%M%S')

    # Character name
    name = extract_with_regex(text, r"CHARACTER NAME[:\s]*([^\n]+)", "")
    if not name:
        # Try alternative formats
        name = extract_with_regex(text, r"Name[:\s]*([^\n]+)", "")

    # Race
    race = extract_with_regex(text, r"RACE[:\s]*([^\n]+)", "")

    # Class and level
    class_level = extract_with_regex(text, r"CLASS [&\+]+ LEVEL[:\s]*([^\n]+)", "")
    character_class = ""
    level = 1

    if class_level:
        # Try to extract class and level
        match = re.search(r"([a-zA-Z\s]+)[^\d]*(\d+)", class_level)
        if match:
            character_class = match.group(1).strip()
            level = int(match.group(2))
        else:
            character_class = class_level

    # Background
    background = extract_with_regex(text, r"BACKGROUND[:\s]*([^\n]+)", "")

    # Ability scores - look for numerical values near ability names
    abilities = {
        'strength': extract_ability_score(text, r"STRENGTH\s*(?:\+\d+|\-\d+)?\s*(\d+)"),
        'dexterity': extract_ability_score(text, r"DEXTERITY\s*(?:\+\d+|\-\d+)?\s*(\d+)"),
        'constitution': extract_ability_score(text, r"CONSTITUTION\s*(?:\+\d+|\-\d+)?\s*(\d+)"),
        'intelligence': extract_ability_score(text, r"INTELLIGENCE\s*(?:\+\d+|\-\d+)?\s*(\d+)"),
        'wisdom': extract_ability_score(text, r"WISDOM\s*(?:\+\d+|\-\d+)?\s*(\d+)"),
        'charisma': extract_ability_score(text, r"CHARISMA\s*(?:\+\d+|\-\d+)?\s*(\d+)")
    }

    # Calculate ability modifiers
    ability_modifiers = {
        ability: calculate_ability_modifier(score)
        for ability, score in abilities.items()
    }

    # HP
    hp_max = extract_with_regex(text, r"Hit Point Maximum[:\s]*(\d+)", 10, int)
    if not hp_max:
        hp_max = extract_with_regex(text, r"HP Max[:\s]*(\d+)", 10, int)

    hp_current = extract_with_regex(text, r"CURRENT HIT POINTS[:\s]*(\d+)", hp_max, int)
    if not hp_current:
        hp_current = extract_with_regex(text, r"HP Current[:\s]*(\d+)", hp_max, int)

    # Armor Class
    armor_class = extract_with_regex(text, r"ARMOR CLASS[:\s]*(\d+)", 10, int)
    if not armor_class:
        armor_class = extract_with_regex(text, r"AC[:\s]*(\d+)", 10, int)

    # Proficiency Bonus
    proficiency_bonus = extract_with_regex(text, r"PROFICIENCY BONUS[:\s]*(?:\+)?(\d+)", 2, int)
    if not proficiency_bonus:
        proficiency_bonus = extract_with_regex(text, r"Prof(?:iciency)? Bonus[:\s]*(?:\+)?(\d+)", 2, int)

    # Skills - Check for marked skills
    skill_proficiencies = []
    skill_list = [
        'Acrobatics', 'Animal Handling', 'Arcana', 'Athletics',
        'Deception', 'History', 'Insight', 'Intimidation',
        'Investigation', 'Medicine', 'Nature', 'Perception',
        'Performance', 'Persuasion', 'Religion', 'Sleight of Hand',
        'Stealth', 'Survival'
    ]

    skills_section = extract_section(text, "SKILLS", ["PASSIVE", "WEAPONS", "ATTACKS", "EQUIPMENT"])

    for skill in skill_list:
        # Look for skill names with potential marks before them
        skill_pattern = r"[☑✓XO\*\+\.\[\(\{].*?" + re.escape(skill)
        if re.search(skill_pattern, skills_section, re.IGNORECASE):
            skill_proficiencies.append(skill)

    # Define which ability each skill is based on
    skill_abilities = {
        'Acrobatics': 'dexterity',
        'Animal Handling': 'wisdom',
        'Arcana': 'intelligence',
        'Athletics': 'strength',
        'Deception': 'charisma',
        'History': 'intelligence',
        'Insight': 'wisdom',
        'Intimidation': 'charisma',
        'Investigation': 'intelligence',
        'Medicine': 'wisdom',
        'Nature': 'intelligence',
        'Perception': 'wisdom',
        'Performance': 'charisma',
        'Persuasion': 'charisma',
        'Religion': 'intelligence',
        'Sleight of Hand': 'dexterity',
        'Stealth': 'dexterity',
        'Survival': 'wisdom'
    }

    # Create skill objects with name, proficiency, and bonus
    skills = []
    for skill_name, ability in skill_abilities.items():
        # Check if the character is proficient in this skill
        is_proficient = skill_name in skill_proficiencies

        # Calculate the bonus
        bonus = ability_modifiers[ability]
        if is_proficient:
            bonus += proficiency_bonus

        # Create a skill object with all relevant information
        skills.append({
            'name': skill_name,
            'ability': ability,
            'proficient': is_proficient,
            'bonus': bonus
        })

    # Equipment
    equipment = []
    equipment_section = extract_section(text, "EQUIPMENT", ["FEATURES", "TRAITS", "CHARACTER"])
    if equipment_section:
        # Clean up and split the equipment section
        equipment_lines = equipment_section.split('\n')
        for line in equipment_lines:
            if line.strip() and not line.strip().upper() == "EQUIPMENT":
                equipment.append(line.strip())

    # Spells (if any)
    spells = []
    spells_section = extract_section(text, "SPELLS", ["CANTRIPS", "SLOTS", "CLASS"])
    if spells_section:
        spell_lines = spells_section.split('\n')
        for line in spell_lines:
            if line.strip() and not line.strip().upper() == "SPELLS":
                # Remove checkbox symbols and clean up
                clean_line = re.sub(r"[☐☑✓XO\*\+\.\[\(\{]", "", line).strip()
                if clean_line:
                    spells.append(clean_line)

    # Traits
    traits = extract_section(text, "PERSONALITY TRAITS", ["IDEALS", "BONDS", "FLAWS"])

    # Assemble character data
    character_data = {
        'id': character_id,
        'name': name,
        'race': race,
        'class': character_class,
        'level': level,
        'abilities': abilities,
        'ability_modifiers': ability_modifiers,
        'hp': {
            'max': hp_max,
            'current': hp_current
        },
        'armor_class': armor_class,
        'proficiency_bonus': proficiency_bonus,
        'skills': skills,
        'equipment': equipment,
        'spells': spells,
        'background': background,
        'traits': traits
    }

    return character_data


def calculate_ability_modifier(ability_score):
    """
    Calculate the ability modifier based on an ability score.

    Args:
        ability_score (int): The ability score (1-30)

    Returns:
        int: The calculated modifier
    """
    return (ability_score - 10) // 2


def extract_with_regex(text, pattern, default=None, type_func=None, flags=0):
    """
    Extract data using regex pattern.

    Args:
        text (str): Text to search in
        pattern (str): Regex pattern
        default: Default value if not found
        type_func: Function to convert the result
        flags: Regex flags

    Returns:
        Extracted value or default
    """
    match = re.search(pattern, text, flags)
    if match:
        value = match.group(1).strip()
        if type_func:
            try:
                return type_func(value)
            except ValueError:
                return default
        return value
    return default


def extract_ability_score(text, pattern):
    """
    Extract ability score using regex pattern.

    Args:
        text (str): Text to search in
        pattern (str): Regex pattern

    Returns:
        int: Ability score (default: 10)
    """
    match = re.search(pattern, text)
    if match:
        try:
            return int(match.group(1))
        except (ValueError, IndexError):
            pass

    # Try alternate patterns if the main one fails
    alt_patterns = [
        r"(STR|DEX|CON|INT|WIS|CHA)(?:\s|\()?(\d+)",
        r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)(?:\s|\()?(\d+)"
    ]

    for alt_pattern in alt_patterns:
        match = re.search(alt_pattern, text)
        if match:
            try:
                return int(match.group(2))
            except (ValueError, IndexError):
                pass

    return 10


def extract_section(text, section_name, end_markers):
    """
    Extract a section of text between a section name and any of the end markers.

    Args:
        text (str): Full text
        section_name (str): Name of the section to extract
        end_markers (list): List of potential end markers

    Returns:
        str: Extracted section text
    """
    # Create pattern to find the section
    pattern = rf"{re.escape(section_name)}(.*?)(?:{'|'.join(re.escape(m) for m in end_markers)}|$)"

    # Extract section
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""

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

    # Class and level - IMPROVED EXTRACTION
    class_level = extract_with_regex(text, r"CLASS [&\+]+ LEVEL[:\s]*([^\n]+)", "")
    character_class = ""
    character_level = 1

    # Try direct level extraction first
    level_field = extract_with_regex(text, r"LEVEL[:\s]*([^\n]+)", "")
    if level_field:
        try:
            level_match = re.search(r'\d+', level_field)
            if level_match:
                character_level = int(level_match.group())
        except (ValueError, AttributeError):
            # If direct extraction fails, continue with class_level parsing
            pass

    if class_level:
        # Try to extract class and level
        match = re.search(r"([a-zA-Z\s]+)[^\d]*(\d+)", class_level)
        if match:
            character_class = match.group(1).strip()
            try:
                # Only update level if we successfully parse it
                parsed_level = int(match.group(2))
                character_level = parsed_level
            except ValueError:
                pass
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

    # Spellcasting information
    spellcasting_class = extract_with_regex(text, r"SPELLCASTING CLASS[:\s]*([^\n]+)", "")
    if not spellcasting_class and is_spellcaster(character_class):
        spellcasting_class = character_class

    # Determine spellcasting ability
    spellcasting_ability = extract_with_regex(text, r"SPELLCASTING ABILITY[:\s]*([^\n]+)", "")
    if not spellcasting_ability:
        spellcasting_ability = determine_spellcasting_ability(spellcasting_class)

    # Extract spell save DC and spell attack bonus
    spell_save_dc = extract_with_regex(text, r"SPELL SAVE DC[:\s]*(\d+)", 0, int)
    spell_attack_bonus = extract_with_regex(text, r"SPELL ATTACK BONUS[:\s]*(?:\+)?(\d+)", 0, int)

    # Calculate if not found and we have a spellcasting class and ability
    if spell_save_dc == 0 and spellcasting_ability and spellcasting_ability in ability_modifiers:
        ability_mod = ability_modifiers[spellcasting_ability]
        spell_save_dc = 8 + proficiency_bonus + ability_mod
        spell_attack_bonus = proficiency_bonus + ability_mod

    # Extract spell slots
    spell_slots = extract_spell_slots_from_text(text, character_level, character_class)

    # Extract spells
    spells_section = extract_section(text, "SPELLS", ["CANTRIPS", "SLOTS", "CLASS"])
    cantrips = []
    spells = []

    # Try to find cantrips section
    cantrips_section = extract_section(text, "CANTRIPS", ["LEVEL 1", "1ST LEVEL", "SPELL LEVEL"])
    if cantrips_section:
        # Extract cantrips
        cantrip_lines = cantrips_section.strip().split('\n')
        for line in cantrip_lines:
            clean_line = re.sub(r"[☐☑✓XO\*\+\.\[\(\{]", "", line).strip()
            if clean_line and not clean_line.upper() == "CANTRIPS":
                cantrips.append(clean_line)

    # Try to find spell levels 1-9
    for level_num in range(1, 10):
        # Different possible headers for spell levels
        level_headers = [
            f"LEVEL {level_num}",
            f"{level_num}ST LEVEL" if level_num == 1 else f"{level_num}ND LEVEL" if level_num == 2 else f"{level_num}RD LEVEL" if level_num == 3 else f"{level_num}TH LEVEL",
            f"SPELL LEVEL {level_num}"
        ]

        # End markers for this section
        end_markers = [f"LEVEL {level_num + 1}",
                       f"{level_num + 1}ST LEVEL" if level_num + 1 == 1 else f"{level_num + 1}ND LEVEL" if level_num + 1 == 2 else f"{level_num + 1}RD LEVEL" if level_num + 1 == 3 else f"{level_num + 1}TH LEVEL"]

        # Try each possible header
        level_section = ""
        for header in level_headers:
            level_section = extract_section(spells_section, header, end_markers + ["CANTRIPS", "TOTAL", "SLOTS"])
            if level_section:
                break

        if level_section:
            # Extract spells for this level
            spell_lines = level_section.strip().split('\n')
            for line in spell_lines:
                clean_line = re.sub(r"[☐☑✓XO\*\+\.\[\(\{]", "", line).strip()
                if clean_line and not any(header.lower() in clean_line.lower() for header in level_headers):
                    spells.append({
                        'name': clean_line,
                        'level': level_num
                    })

    # Fallback: if we couldn't parse spell levels, just add all spells without levels
    if not spells and not cantrips and spells_section:
        spell_lines = spells_section.strip().split('\n')
        for line in spell_lines:
            clean_line = re.sub(r"[☐☑✓XO\*\+\.\[\(\{]", "", line).strip()
            if clean_line and not clean_line.upper() == "SPELLS":
                spells.append({
                    'name': clean_line,
                    'level': 1  # Default to level 1
                })

    # Create spellcasting data structure
    spellcasting = {
        'class': spellcasting_class,
        'ability': spellcasting_ability,
        'spell_save_dc': spell_save_dc,
        'spell_attack_bonus': spell_attack_bonus,
        'spell_slots': spell_slots,
        'cantrips': cantrips,
        'spells': spells
    }

    # Traits
    traits = extract_section(text, "PERSONALITY TRAITS", ["IDEALS", "BONDS", "FLAWS"])

    # Assemble character data
    character_data = {
        'id': character_id,
        'name': name,
        'race': race,
        'class': character_class,
        'level': character_level,  # Using the correct variable name
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
        'spellcasting': spellcasting,
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


def is_spellcaster(character_class):
    """
    Determine if a class is a spellcaster.

    Args:
        character_class (str): Character class name

    Returns:
        bool: True if the class can cast spells
    """
    if not character_class:
        return False

    # Standard spellcasting classes
    full_casters = ['wizard', 'sorcerer', 'bard', 'cleric', 'druid']
    half_casters = ['paladin', 'ranger', 'artificer']
    third_casters = ['eldritch knight', 'arcane trickster']

    # Normalize the class name
    class_lower = character_class.lower()

    # Check if the class is a spellcaster
    return (any(caster in class_lower for caster in full_casters) or
            any(caster in class_lower for caster in half_casters) or
            any(caster in class_lower for caster in third_casters) or
            'warlock' in class_lower)


def determine_spellcasting_ability(character_class):
    """
    Determine the spellcasting ability for a class.

    Args:
        character_class (str): Character class name

    Returns:
        str: Spellcasting ability or empty string if not a spellcaster
    """
    if not character_class:
        return ""

    # Normalize the class name
    class_lower = character_class.lower()

    # Intelligence-based casters
    if any(c in class_lower for c in ['wizard', 'artificer', 'eldritch knight', 'arcane trickster']):
        return 'intelligence'

    # Wisdom-based casters
    if any(c in class_lower for c in ['cleric', 'druid', 'ranger']):
        return 'wisdom'

    # Charisma-based casters
    if any(c in class_lower for c in ['bard', 'sorcerer', 'paladin', 'warlock']):
        return 'charisma'

    return ""


def extract_spell_slots_from_text(text, level, character_class):
    """
    Extract spell slot information from OCR text.

    Args:
        text (str): OCR text
        level (int): Character level
        character_class (str): Character class

    Returns:
        dict: Spell slots data structure
    """
    # Initialize spell slots
    spell_slots = {}
    for slot_level in range(1, 10):
        spell_slots[str(slot_level)] = {
            'total': 0,
            'used': 0
        }

    # Try to find spell slots section
    slots_section = extract_section(text, "SPELL SLOTS", ["CANTRIPS", "SPELLS", "SPELL NAME"])

    # Try to extract spell slots from text
    for slot_level in range(1, 10):
        # Look for patterns like "1st level: 4/4" or similar
        level_patterns = [
            rf"{slot_level}(?:st|nd|rd|th)?\s*(?:level)?[:\s]*(\d+)[^\d]*(\d+)",
            rf"Level\s*{slot_level}[:\s]*(\d+)[^\d]*(\d+)"
        ]

        for pattern in level_patterns:
            match = re.search(pattern, slots_section, re.IGNORECASE)
            if match:
                try:
                    # The first number is usually the total, the second is used
                    total = int(match.group(1))
                    used = int(match.group(2))
                    spell_slots[str(slot_level)]['total'] = total
                    spell_slots[str(slot_level)]['used'] = used
                    break
                except (ValueError, IndexError):
                    pass

    # Alternative pattern: look for "Total X" and "Expended Y" rows
    if all(spell_slots[str(i)]['total'] == 0 for i in range(1, 10)):
        for slot_level in range(1, 10):
            total_pattern = rf"(?:Level\s*{slot_level}|{slot_level}(?:st|nd|rd|th)?).*?(?:Total|TOTAL)[:\s]*(\d+)"
            expended_pattern = rf"(?:Level\s*{slot_level}|{slot_level}(?:st|nd|rd|th)?).*?(?:Expended|EXPENDED|Used|USED)[:\s]*(\d+)"

            # Extract total slots
            match = re.search(total_pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                try:
                    spell_slots[str(slot_level)]['total'] = int(match.group(1))
                except (ValueError, IndexError):
                    pass

            # Extract used slots
            match = re.search(expended_pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                try:
                    spell_slots[str(slot_level)]['used'] = int(match.group(1))
                except (ValueError, IndexError):
                    pass

    # If we still couldn't find spell slots, calculate them based on class and level
    if all(spell_slots[str(i)]['total'] == 0 for i in range(1, 10)) and is_spellcaster(character_class):
        calculate_default_spell_slots(spell_slots, level, character_class)

    return spell_slots


def calculate_default_spell_slots(spell_slots, level, character_class):
    """
    Calculate default spell slots based on class and level.

    Args:
        spell_slots (dict): Spell slots dictionary to update
        level (int): Character level
        character_class (str): Character class
    """
    class_lower = character_class.lower()

    # Full casters: wizard, sorcerer, bard, cleric, druid
    if any(c in class_lower for c in ['wizard', 'sorcerer', 'bard', 'cleric', 'druid']):
        calculate_full_caster_slots(spell_slots, level)

    # Half casters: paladin, ranger, artificer
    elif any(c in class_lower for c in ['paladin', 'ranger', 'artificer']):
        calculate_half_caster_slots(spell_slots, level)

    # Warlock (special case)
    elif 'warlock' in class_lower:
        calculate_warlock_slots(spell_slots, level)

    # Third casters: eldritch knight, arcane trickster
    elif any(c in class_lower for c in ['eldritch knight', 'arcane trickster']):
        calculate_third_caster_slots(spell_slots, level)


def calculate_full_caster_slots(spell_slots, level):
    """
    Calculate spell slots for full casters.

    Args:
        spell_slots (dict): Spell slots dictionary to update
        level (int): Character level
    """
    # Spell slots by level for full casters
    full_caster_slots = {
        1: {'1': 2},
        2: {'1': 3},
        3: {'1': 4, '2': 2},
        4: {'1': 4, '2': 3},
        5: {'1': 4, '2': 3, '3': 2},
        6: {'1': 4, '2': 3, '3': 3},
        7: {'1': 4, '2': 3, '3': 3, '4': 1},
        8: {'1': 4, '2': 3, '3': 3, '4': 2},
        9: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 1},
        10: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2},
        11: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2, '6': 1},
        12: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2, '6': 1},
        13: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2, '6': 1, '7': 1},
        14: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2, '6': 1, '7': 1},
        15: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2, '6': 1, '7': 1, '8': 1},
        16: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2, '6': 1, '7': 1, '8': 1},
        17: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 2, '6': 1, '7': 1, '8': 1, '9': 1},
        18: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 3, '6': 1, '7': 1, '8': 1, '9': 1},
        19: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 3, '6': 2, '7': 1, '8': 1, '9': 1},
        20: {'1': 4, '2': 3, '3': 3, '4': 3, '5': 3, '6': 2, '7': 2, '8': 1, '9': 1}
    }

    # Get the slots for the character level (cap at 20)
    level_slots = full_caster_slots.get(min(level, 20), {})

    # Update the spell slots dictionary
    for slot_level, count in level_slots.items():
        spell_slots[slot_level]['total'] = count


def calculate_half_caster_slots(spell_slots, level):
    """
    Calculate spell slots for half casters (paladin, ranger).

    Args:
        spell_slots (dict): Spell slots dictionary to update
        level (int): Character level
    """
    # Treat as half the full caster level (rounded up, but starting from level 2)
    caster_level = (level - 1) // 2 + 1 if level > 1 else 0

    # Use full caster table with the modified level
    if caster_level > 0:
        calculate_full_caster_slots(spell_slots, caster_level)

    # Half casters only get up to 5th level spells
    for slot_level in range(6, 10):
        spell_slots[str(slot_level)]['total'] = 0


def calculate_warlock_slots(spell_slots, level):
    """
    Calculate spell slots for warlocks.

    Args:
        spell_slots (dict): Spell slots dictionary to update
        level (int): Character level
    """
    # Warlock spell slots by level
    warlock_slots = {
        1: {'1': 1},
        2: {'1': 2},
        3: {'2': 2},
        4: {'2': 2},
        5: {'3': 2},
        6: {'3': 2},
        7: {'4': 2},
        8: {'4': 2},
        9: {'5': 2},
        10: {'5': 2},
        11: {'5': 3},
        12: {'5': 3},
        13: {'5': 3},
        14: {'5': 3},
        15: {'5': 3},
        16: {'5': 3},
        17: {'5': 4},
        18: {'5': 4},
        19: {'5': 4},
        20: {'5': 4}
    }

    # Get the slots for the character level
    level_slots = warlock_slots.get(min(level, 20), {})

    # Update the spell slots dictionary
    for slot_level, count in level_slots.items():
        spell_slots[slot_level]['total'] = count

    # Get mystic arcanum for higher level spells
    if level >= 11:
        spell_slots['6']['total'] = 1
    if level >= 13:
        spell_slots['7']['total'] = 1
    if level >= 15:
        spell_slots['8']['total'] = 1
    if level >= 17:
        spell_slots['9']['total'] = 1


def calculate_third_caster_slots(spell_slots, level):
    """
    Calculate spell slots for third casters (Eldritch Knight, Arcane Trickster).

    Args:
        spell_slots (dict): Spell slots dictionary to update
        level (int): Character level
    """
    # Calculate equivalent full caster level (one-third)
    caster_level = level // 3

    # Use full caster table with the modified level
    if caster_level > 0:
        calculate_full_caster_slots(spell_slots, caster_level)

    # Third casters only get up to 4th level spells
    for slot_level in range(5, 10):
        spell_slots[str(slot_level)]['total'] = 0

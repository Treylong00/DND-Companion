import os
import json
from datetime import datetime
import PyPDF2
import re


def import_character_from_pdf(pdf_path, data_dir):
    """
    Import a D&D character from a fillable PDF form.

    Args:
        pdf_path (str): Path to the PDF file
        data_dir (str): Directory to save the character data

    Returns:
        tuple: (character_id, error_message)
    """
    try:
        # Open the PDF
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)

            # Check if it has form fields
            form_fields = reader.get_form_text_fields()
            if not form_fields or len(form_fields) == 0:
                return None, "No fillable form fields found in the PDF"

            # Debug: Print form fields
            # print("Form fields found:", form_fields)

            # Extract character data from form fields
            character_data = extract_character_data(form_fields)

            # Save the character data
            character_path = os.path.join(data_dir, f"{character_data['id']}.json")
            with open(character_path, 'w') as outfile:
                json.dump(character_data, outfile, indent=2)

            return character_data['id'], None

    except Exception as e:
        return None, f"Error processing PDF: {str(e)}"


def extract_character_data(form_fields):
    """
    Extract character data from PDF form fields.

    Args:
        form_fields (dict): Form fields extracted from the PDF

    Returns:
        dict: Character data
    """
    # Generate a unique ID for the character
    character_id = datetime.now().strftime('%Y%m%d%H%M%S')

    # Character name
    character_name = get_field_value(form_fields, ['CharacterName'])

    # Race
    race = get_field_value(form_fields, ['Race'])

    # Class and level
    class_level = get_field_value(form_fields, ['ClassLevel'])
    character_class = ''
    level = 1

    if class_level:
        # Try to extract class and level (e.g., "Barbarian 1")
        match = re.match(r"([a-zA-Z\s]+)\s*(\d+)", class_level)
        if match:
            character_class = match.group(1).strip()
            level = int(match.group(2))
        else:
            character_class = class_level

    # Background
    background = get_field_value(form_fields, ['Background'])

    # Ability scores
    abilities = {
        'strength': parse_int(get_field_value(form_fields, ['STR', 'Strength']), 10),
        'dexterity': parse_int(get_field_value(form_fields, ['DEX', 'Dexterity']), 10),
        'constitution': parse_int(get_field_value(form_fields, ['CON', 'Constitution']), 10),
        'intelligence': parse_int(get_field_value(form_fields, ['INT', 'Intelligence']), 10),
        'wisdom': parse_int(get_field_value(form_fields, ['WIS', 'Wisdom']), 10),
        'charisma': parse_int(get_field_value(form_fields, ['CHA', 'Charisma']), 10)
    }

    # Calculate ability modifiers
    ability_modifiers = {
        ability: calculate_ability_modifier(score)
        for ability, score in abilities.items()
    }

    # HP
    hp_max = parse_int(get_field_value(form_fields, ['HPMax', 'Hit Point Maximum']), 10)
    hp_current = parse_int(get_field_value(form_fields, ['HPCurrent', 'CURRENT HIT POINTS']), hp_max)

    # Armor Class
    armor_class = parse_int(get_field_value(form_fields, ['AC', 'ARMOR CLASS']), 10)

    # Proficiency Bonus
    proficiency_bonus = parse_int(get_field_value(form_fields, ['ProfBonus', 'PROFICIENCY BONUS']), 2)

    # Skills with proficiency
    skill_proficiencies = []
    skill_mapping = {
        'Acrobatics': ['Acrobatics'],
        'Animal Handling': ['Animal', 'AnimalHandling', 'AnimalHandli'],
        'Arcana': ['Arcana'],
        'Athletics': ['Athletics'],
        'Deception': ['Deception'],
        'History': ['History'],
        'Insight': ['Insight'],
        'Intimidation': ['Intimidation'],
        'Investigation': ['Investigation'],
        'Medicine': ['Medicine'],
        'Nature': ['Nature'],
        'Perception': ['Perception'],
        'Performance': ['Performance'],
        'Persuasion': ['Persuasion'],
        'Religion': ['Religion'],
        'Sleight of Hand': ['SleightofHand', 'Sleight of Hand', 'SleightHand'],
        'Stealth': ['Stealth'],
        'Survival': ['Survival']
    }

    # Check for skills based on the shown pattern
    for field in form_fields:
        # Check for "Skill-CB-X" pattern (checked skill checkboxes)
        if field.startswith('Skill-CB-') and form_fields[field]:
            # Extract skill name from the field
            skill_key = field.replace('Skill-CB-', '')

            # Match it to our known skills
            matched = False
            for skill_name, field_names in skill_mapping.items():
                if any(skill_key.lower() == name.lower() or
                       skill_key.lower() in name.lower() or
                       name.lower() in skill_key.lower()
                       for name in field_names):
                    skill_proficiencies.append(skill_name)
                    matched = True
                    break

            # If we couldn't match it to our mapping, add it directly
            if not matched:
                skill_proficiencies.append(skill_key)

    # If no skills found with the CB format, try other common formats
    if not skill_proficiencies:
        # Check each skill
        for skill_name, field_names in skill_mapping.items():
            # Look for checkbox fields related to skills
            for field_name in field_names:
                # Common patterns for skill checkboxes
                checkbox_patterns = [
                    f'Check Box {field_name}',
                    f'CheckBox{field_name}',
                    f'{field_name}Prof',
                    f'{field_name} Prof',
                    f'Skill - {field_name}'
                ]

                for pattern in checkbox_patterns:
                    if any(pattern in field for field in form_fields):
                        for field in form_fields:
                            if pattern in field and form_fields[field]:
                                skill_proficiencies.append(skill_name)
                                break

    # Calculate skill bonuses based on ability modifiers and proficiency
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
    equipment_text = get_field_value(form_fields, ['Equipment', 'EQUIPMENT'])
    if equipment_text:
        equipment = [item.strip() for item in equipment_text.split('\n') if item.strip()]

    # Spells
    spells = []
    spells_text = get_field_value(form_fields, ['Spells', 'SPELLS'])
    if spells_text:
        spells = [item.strip() for item in spells_text.split('\n') if item.strip()]

    # Traits
    traits = get_field_value(form_fields, ['PersonalityTraits', 'PERSONALITY TRAITS'])

    # Assemble character data
    character_data = {
        'id': character_id,
        'name': character_name,
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


def get_field_value(form_fields, field_names):
    """
    Try to get a value from multiple possible field names.

    Args:
        form_fields (dict): Form fields dictionary
        field_names (list): List of possible field names

    Returns:
        str: Field value or empty string if not found
    """
    for name in field_names:
        # Try exact match
        if name in form_fields and form_fields[name]:
            return form_fields[name]

        # Try case-insensitive match
        for field in form_fields:
            if field.lower() == name.lower() and form_fields[field]:
                return form_fields[field]

        # Try partial match
        for field in form_fields:
            if name.lower() in field.lower() and form_fields[field]:
                return form_fields[field]

    return ""


def parse_int(value, default=0):
    """
    Parse an integer from a string, handling various formats.

    Args:
        value (str): String to parse
        default (int): Default value if parsing fails

    Returns:
        int: Parsed integer or default
    """
    if not value:
        return default

    try:
        # Remove non-numeric characters (except minus sign)
        clean_value = ''.join(c for c in value if c.isdigit() or c == '-')
        if clean_value:
            return int(clean_value)
        return default
    except ValueError:
        return default

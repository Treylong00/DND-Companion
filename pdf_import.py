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

    # Class and level - IMPROVED EXTRACTION
    class_level = get_field_value(form_fields, ['ClassLevel'])
    character_class = ''
    character_level = 1  # Default level

    # Try direct level extraction first
    level_field = get_field_value(form_fields, ['Level', 'CharacterLevel'])
    if level_field:
        try:
            level_match = re.search(r'\d+', level_field)
            if level_match:
                character_level = int(level_match.group())
        except (ValueError, AttributeError):
            # If direct extraction fails, continue with class_level parsing
            pass

    if class_level:
        # Try to extract class and level (e.g., "Wizard 5")
        match = re.search(r"([a-zA-Z\s]+)\s*(\d+)", class_level)
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

    # Spellcasting information
    spellcasting_class = get_field_value(form_fields, ['SpellcastingClass'])
    if not spellcasting_class and is_spellcaster(character_class):
        spellcasting_class = character_class

    # Determine spellcasting ability
    spellcasting_ability = determine_spellcasting_ability(spellcasting_class)

    # Calculate spell save DC and spell attack bonus
    spell_save_dc = 0
    spell_attack_bonus = 0

    if spellcasting_ability and spellcasting_ability in ability_modifiers:
        ability_mod = ability_modifiers[spellcasting_ability]
        spell_save_dc = 8 + proficiency_bonus + ability_mod
        spell_attack_bonus = proficiency_bonus + ability_mod

    # Extract spell slots information
    spell_slots = extract_spell_slots(form_fields, character_level, character_class)

    # Spells known or prepared
    spells = []
    cantrips = []

    # Try extracting spells from a spell list section
    spells_text = get_field_value(form_fields, ['Spells', 'SPELLS'])
    if spells_text:
        spell_lines = [item.strip() for item in spells_text.split('\n') if item.strip()]

        # Try to categorize spells by level
        current_level = 0
        for line in spell_lines:
            # Check if this line indicates a spell level
            level_match = re.match(r'(cantrips?|level\s*\d+)', line.lower())
            if level_match:
                level_text = level_match.group(1)
                if 'cantrip' in level_text:
                    current_level = 0
                else:
                    level_digits = re.search(r'\d+', level_text)
                    current_level = parse_int(level_digits.group(0) if level_digits else "1", 1)
                continue

            # Add spell to appropriate list
            if current_level == 0:
                cantrips.append(line)
            else:
                spells.append({
                    'name': line,
                    'level': current_level
                })
    else:
        # Try extracting individual spells from separate form fields
        # Common patterns for spell fields
        cantrip_patterns = ['Cantrip', 'Cantrips', 'Level0']
        for field in form_fields:
            if any(pattern in field for pattern in cantrip_patterns) and form_fields[field]:
                cantrips.append(form_fields[field])

        # Spells of levels 1-9
        for spell_level in range(1, 10):
            level_patterns = [f'Level{spell_level}', f'L{spell_level}Spells', f'Spell{spell_level}']
            for field in form_fields:
                if any(pattern in field for pattern in level_patterns) and form_fields[field]:
                    spells.append({
                        'name': form_fields[field],
                        'level': spell_level
                    })

    # Spellcasting data structure
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
    traits = get_field_value(form_fields, ['PersonalityTraits', 'PERSONALITY TRAITS'])

    # Assemble character data
    character_data = {
        'id': character_id,
        'name': character_name,
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


def extract_spell_slots(form_fields, level, character_class):
    """
    Extract spell slot information from the form fields.

    Args:
        form_fields (dict): Form fields dictionary
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

    # Try to extract spell slots from form fields
    for slot_level in range(1, 10):
        # Look for fields that might contain spell slot information
        total_patterns = [
            f'SlotsTotal{slot_level}',
            f'SpellSlots{slot_level}',
            f'Level{slot_level}SlotsTotal'
        ]

        used_patterns = [
            f'SlotsExpended{slot_level}',
            f'SpellSlotsUsed{slot_level}',
            f'Level{slot_level}SlotsExpended'
        ]

        # Extract total slots
        for pattern in total_patterns:
            value = get_field_value(form_fields, [pattern])
            if value:
                spell_slots[str(slot_level)]['total'] = parse_int(value, 0)
                break

        # Extract used slots
        for pattern in used_patterns:
            value = get_field_value(form_fields, [pattern])
            if value:
                spell_slots[str(slot_level)]['used'] = parse_int(value, 0)
                break

    # If we couldn't find spell slots in the form, calculate them based on class and level
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
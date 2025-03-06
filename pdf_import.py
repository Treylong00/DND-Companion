from PyPDF2 import PdfReader
import re
import os
import json
from datetime import datetime
from flask import flash


def extract_fields_from_pdf(pdf_file):
    """
    Extract form fields from a D&D character sheet PDF

    Args:
        pdf_file: File path of the uploaded PDF

    Returns:
        Dictionary containing character data extracted from the PDF
    """
    try:
        reader = PdfReader(pdf_file)

        # Get the form fields
        fields = reader.get_form_text_fields()

        if not fields:
            return None, "No fillable form fields found in the PDF."

        # Map PDF fields to our character data structure
        # This mapping will need to be adjusted based on the specific PDF form being used
        character_data = {
            "id": datetime.now().strftime('%Y%m%d%H%M%S'),
            "name": fields.get("CharacterName", ""),
            "race": fields.get("Race", ""),
            "class": fields.get("ClassLevel", "").split()[0] if fields.get("ClassLevel", "") else "",
            "level": extract_level(fields.get("ClassLevel", "")),
            "abilities": {
                "strength": extract_integer(fields.get("STR", "10")),
                "dexterity": extract_integer(fields.get("DEX", "10")),
                "constitution": extract_integer(fields.get("CON", "10")),
                "intelligence": extract_integer(fields.get("INT", "10")),
                "wisdom": extract_integer(fields.get("WIS", "10")),
                "charisma": extract_integer(fields.get("CHA", "10"))
            },
            "hp": {
                "max": extract_integer(fields.get("HPMax", "10")),
                "current": extract_integer(fields.get("HPCurrent", "10"))
            },
            "armor_class": extract_integer(fields.get("AC", "10")),
            "proficiency_bonus": extract_integer(fields.get("ProfBonus", "2")),
            "skills": extract_skills(fields),
            "equipment": extract_equipment(fields),
            "spells": extract_spells(fields),
            "background": fields.get("Background", ""),
            "traits": extract_traits(fields)
        }

        return character_data, None
    except Exception as e:
        return None, f"Error processing PDF: {str(e)}"


def extract_level(class_level_text):
    """Extract level from class/level text"""
    if not class_level_text:
        return 1

    # Try to find a number in the string
    level_match = re.search(r'\d+', class_level_text)
    if level_match:
        return int(level_match.group())
    return 1


def extract_integer(value, default=0):
    """Extract an integer from a string, with fallback default"""
    if not value:
        return default

    # Remove any non-digit characters
    digits = re.sub(r'\D', '', value)
    if digits:
        return int(digits)
    return default


def extract_skills(fields):
    """Extract checked skills from form fields"""
    skills = []
    skill_map = {
        "Acrobatics": ["Acrobatics", "AcrobaticsProf", "SkillsAcrobatics"],
        "Animal Handling": ["AnimalHandling", "AnimalHandlingProf", "SkillsAnimal"],
        "Arcana": ["Arcana", "ArcanaProf", "SkillsArcana"],
        "Athletics": ["Athletics", "AthleticsProf", "SkillsAthletics"],
        "Deception": ["Deception", "DeceptionProf", "SkillsDeception"],
        "History": ["History", "HistoryProf", "SkillsHistory"],
        "Insight": ["Insight", "InsightProf", "SkillsInsight"],
        "Intimidation": ["Intimidation", "IntimidationProf", "SkillsIntimidation"],
        "Investigation": ["Investigation", "InvestigationProf", "SkillsInvestigation"],
        "Medicine": ["Medicine", "MedicineProf", "SkillsMedicine"],
        "Nature": ["Nature", "NatureProf", "SkillsNature"],
        "Perception": ["Perception", "PerceptionProf", "SkillsPerception"],
        "Performance": ["Performance", "PerformanceProf", "SkillsPerformance"],
        "Persuasion": ["Persuasion", "PersuasionProf", "SkillsPersuasion"],
        "Religion": ["Religion", "ReligionProf", "SkillsReligion"],
        "Sleight of Hand": ["SleightOfHand", "SleightOfHandProf", "SkillsSleight"],
        "Stealth": ["Stealth", "StealthProf", "SkillsStealth"],
        "Survival": ["Survival", "SurvivalProf", "SkillsSurvival"]
    }

    for skill, field_options in skill_map.items():
        # Check multiple possible field names
        for field in field_options:
            if field in fields and fields[field] in ["Yes", "True", "1", "ON", "On", "on", "yes", "true"]:
                skills.append(skill)
                break

    return skills


def extract_equipment(fields):
    """Extract equipment from various fields in the PDF"""
    equipment = []

    # Try common field names for equipment
    equipment_fields = [
        "Equipment", "CP", "SP", "EP", "GP", "PP",
        "Weapons1", "Weapons2", "Weapons3",
        "Equipment1", "Equipment2", "Equipment3", "Equipment4",
    ]

    for field in equipment_fields:
        if field in fields and fields[field]:
            # Special handling for currency
            if field in ["CP", "SP", "EP", "GP", "PP"] and fields[field]:
                currency_name = {"CP": "Copper", "SP": "Silver", "EP": "Electrum", "GP": "Gold", "PP": "Platinum"}
                equipment.append(f"{fields[field]} {currency_name[field]} pieces")
            elif fields[field]:
                equipment.append(fields[field])

    # Look for equipment text in larger text fields
    if "EquipmentNotes" in fields and fields["EquipmentNotes"]:
        for item in fields["EquipmentNotes"].split('\n'):
            if item.strip():
                equipment.append(item.strip())

    # Remove duplicates while preserving order
    unique_equipment = []
    for item in equipment:
        if item and item not in unique_equipment:
            unique_equipment.append(item)

    return unique_equipment


def extract_spells(fields):
    """Extract spells from the PDF"""
    spells = []

    # Check for different spell field patterns
    for key in fields:
        # Look for spell fields with patterns like "Spells1", "Spell_1", etc.
        if any(pattern in key.lower() for pattern in ["spell", "cantrip"]) and fields[key]:
            spells.append(fields[key])

    # If there's a spells text area, parse it line by line
    if "SpellsNotes" in fields and fields["SpellsNotes"]:
        for line in fields["SpellsNotes"].split('\n'):
            if line.strip():
                spells.append(line.strip())

    # Remove duplicates while preserving order
    unique_spells = []
    for spell in spells:
        if spell and spell not in unique_spells:
            unique_spells.append(spell)

    return unique_spells


def extract_traits(fields):
    """Extract character traits from personality fields"""
    traits = []

    trait_fields = [
        "PersonalityTraits", "Ideals", "Bonds", "Flaws",
        "Features", "Traits", "CharacterNotes"
    ]

    for field in trait_fields:
        if field in fields and fields[field]:
            traits.append(f"{field}: {fields[field]}")

    return "\n\n".join(traits)


def import_character_from_pdf(pdf_file, save_dir):
    """
    Process a character sheet PDF and save it to the data directory

    Args:
        pdf_file: File path of the uploaded PDF
        save_dir: Directory to save the processed character data

    Returns:
        tuple: (character_id, error_message)
    """
    character_data, error = extract_fields_from_pdf(pdf_file)

    if error:
        return None, error

    # Verify the character has at least a name
    if not character_data.get("name"):
        character_data["name"] = "Imported Character"

    # Save the character data
    character_id = character_data["id"]
    file_path = os.path.join(save_dir, f"{character_id}.json")

    with open(file_path, 'w') as file:
        json.dump(character_data, file, indent=2)

    return character_id, None
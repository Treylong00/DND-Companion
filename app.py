from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import json
import os
import re
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'dnd_secret_key'  # For flash messages
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit uploads to 16 MB
app.config['UPLOAD_FOLDER'] = 'uploads'  # Temporary folder for uploads

# Create necessary directories if they don't exist
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Character file path helper
def get_character_path(character_id):
    return os.path.join(DATA_DIR, f'{character_id}.json')


# Load all characters
def load_characters():
    characters = []
    if os.path.exists(DATA_DIR):
        for filename in os.listdir(DATA_DIR):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(DATA_DIR, filename), 'r') as file:
                        character = json.load(file)
                        characters.append(character)
                except:
                    pass
    return characters


# Load a specific character
def load_character(character_id):
    file_path = get_character_path(character_id)
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return json.load(file)
    return None


# Save character data
def save_character(character_data):
    character_id = character_data.get('id')
    if not character_id:
        character_id = datetime.now().strftime('%Y%m%d%H%M%S')
        character_data['id'] = character_id

    with open(get_character_path(character_id), 'w') as file:
        json.dump(character_data, file, indent=2)

    return character_id


# Helper function to prepare spell lists for a character
def prepare_spell_lists(character):
    spell_lists = {
        'level1': '',
        'level2': '',
        'level3': '',
        'level4plus': ''
    }

    if character and 'spellcasting' in character and 'spells' in character['spellcasting']:
        level1_spells = []
        level2_spells = []
        level3_spells = []
        level4plus_spells = []

        for spell in character['spellcasting']['spells']:
            if spell['level'] == 1:
                level1_spells.append(spell['name'])
            elif spell['level'] == 2:
                level2_spells.append(spell['name'])
            elif spell['level'] == 3:
                level3_spells.append(spell['name'])
            elif spell['level'] >= 4:
                level4plus_spells.append(f"{spell['name']} (Level {spell['level']})")

        spell_lists['level1'] = '\n'.join(level1_spells)
        spell_lists['level2'] = '\n'.join(level2_spells)
        spell_lists['level3'] = '\n'.join(level3_spells)
        spell_lists['level4plus'] = '\n'.join(level4plus_spells)

    return spell_lists


# Helper function to get proficient skill names
def get_proficient_skill_names(character):
    proficient_skills = []

    if character and 'skills' in character:
        if character['skills'] and isinstance(character['skills'][0], dict):
            # If skills are stored as objects with name and proficient properties
            proficient_skills = [skill['name'] for skill in character['skills'] if skill.get('proficient')]
        else:
            # If skills are stored as simple strings
            proficient_skills = character['skills']

    return proficient_skills


# Routes
@app.route('/')
def index():
    characters = load_characters()
    return render_template('index.html', characters=characters)


@app.route('/import', methods=['GET', 'POST'])
def import_character():
    if request.method == 'POST':
        # Check if a file was uploaded
        if 'pdf_file' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['pdf_file']

        # If the user does not select a file, the browser submits an
        # empty file without a filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        # Check if the file is a PDF
        if file and file.filename.lower().endswith('.pdf'):
            # Save the uploaded file temporarily
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_DIR, filename)
            file.save(file_path)

            try:
                # First try the standard form-fillable PDF import
                try:
                    from pdf_import import import_character_from_pdf
                    character_id, error = import_character_from_pdf(file_path, DATA_DIR)

                    if error and "No fillable form fields found" in error:
                        # If no form fields, try OCR-based import
                        flash('No fillable form fields found. Attempting OCR import...')
                        from ocr_support import import_character_from_scanned_pdf
                        character_id, error = import_character_from_scanned_pdf(file_path, DATA_DIR)
                except ImportError:
                    flash('Standard PDF import failed. Attempting OCR import...')
                    from ocr_support import import_character_from_scanned_pdf
                    character_id, error = import_character_from_scanned_pdf(file_path, DATA_DIR)

                # Remove the temporary file
                if os.path.exists(file_path):
                    os.remove(file_path)

                if error:
                    flash(f'Error importing character: {error}')
                    return redirect(url_for('import_character'))

                flash('Character imported successfully!')
                return redirect(url_for('view_character', character_id=character_id))
            except Exception as e:
                flash(f'Error processing file: {str(e)}')
                return redirect(url_for('import_character'))
        else:
            flash('Only PDF files are allowed')
            return redirect(request.url)

    return render_template('import.html')


@app.route('/character/new', methods=['GET', 'POST'])
def new_character():
    if request.method == 'POST':
        character_data = {
            'name': request.form.get('name', 'Unnamed Character'),
            'race': request.form.get('race', ''),
            'class': request.form.get('class', ''),
            'level': int(request.form.get('level', 1)),
            'abilities': {
                'strength': int(request.form.get('strength', 10)),
                'dexterity': int(request.form.get('dexterity', 10)),
                'constitution': int(request.form.get('constitution', 10)),
                'intelligence': int(request.form.get('intelligence', 10)),
                'wisdom': int(request.form.get('wisdom', 10)),
                'charisma': int(request.form.get('charisma', 10))
            },
            'hp': {
                'max': int(request.form.get('max_hp', 10)),
                'current': int(request.form.get('current_hp', 10))
            },
            'armor_class': int(request.form.get('armor_class', 10)),
            'proficiency_bonus': int(request.form.get('proficiency_bonus', 2)),
            'skills': request.form.getlist('skills'),
            'equipment': request.form.get('equipment', '').split('\n'),
            'spells': request.form.get('spells', '').split('\n'),
            'background': request.form.get('background', ''),
            'traits': request.form.get('traits', '')
        }

        character_id = save_character(character_data)
        flash('Character created successfully!')
        return redirect(url_for('view_character', character_id=character_id))

    return render_template('character_form.html', character=None)


@app.route('/character/<character_id>')
def view_character(character_id):
    character = load_character(character_id)
    if character:
        return render_template('character.html', character=character)
    flash('Character not found!')
    return redirect(url_for('index'))


@app.route('/character/<character_id>/edit', methods=['GET', 'POST'])
def edit_character(character_id):
    character = load_character(character_id)

    if not character:
        flash('Character not found!')
        return redirect(url_for('index'))

    if request.method == 'POST':
        character['name'] = request.form.get('name', character['name'])
        character['race'] = request.form.get('race', character['race'])
        character['class'] = request.form.get('class', character['class'])
        character['level'] = int(request.form.get('level', character['level']))

        # Update abilities
        for ability in ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']:
            character['abilities'][ability] = int(request.form.get(ability, character['abilities'][ability]))

        # Update HP
        character['hp']['max'] = int(request.form.get('max_hp', character['hp']['max']))
        character['hp']['current'] = int(request.form.get('current_hp', character['hp']['current']))

        # Update other fields
        character['armor_class'] = int(request.form.get('armor_class', character['armor_class']))
        character['proficiency_bonus'] = int(request.form.get('proficiency_bonus', character['proficiency_bonus']))
        character['skills'] = request.form.getlist('skills')
        character['equipment'] = request.form.get('equipment', '').split('\n')
        character['background'] = request.form.get('background', '')
        character['traits'] = request.form.get('traits', '')

        # Handle spellcasting data if the character is a spellcaster
        if 'spellcasting' in character:
            # Update spellcasting class and ability
            spellcasting_class = request.form.get('spellcasting_class', '')
            spellcasting_ability = request.form.get('spellcasting_ability', '')

            if spellcasting_class:
                character['spellcasting']['class'] = spellcasting_class

            if spellcasting_ability:
                character['spellcasting']['ability'] = spellcasting_ability

                # Recalculate spell save DC and attack bonus based on the ability
                ability_mod = character['ability_modifiers'][spellcasting_ability]
                character['spellcasting']['spell_save_dc'] = 8 + character['proficiency_bonus'] + ability_mod
                character['spellcasting']['spell_attack_bonus'] = character['proficiency_bonus'] + ability_mod

            # Update cantrips
            cantrips = request.form.get('cantrips', '').split('\n')
            character['spellcasting']['cantrips'] = [c.strip() for c in cantrips if c.strip()]

            # Update spells by level
            new_spells = []

            # Level 1 spells
            level1_spells = request.form.get('spells_level_1', '').split('\n')
            for spell_name in level1_spells:
                if spell_name.strip():
                    new_spells.append({
                        'name': spell_name.strip(),
                        'level': 1
                    })

            # Level 2 spells
            level2_spells = request.form.get('spells_level_2', '').split('\n')
            for spell_name in level2_spells:
                if spell_name.strip():
                    new_spells.append({
                        'name': spell_name.strip(),
                        'level': 2
                    })

            # Level 3 spells
            level3_spells = request.form.get('spells_level_3', '').split('\n')
            for spell_name in level3_spells:
                if spell_name.strip():
                    new_spells.append({
                        'name': spell_name.strip(),
                        'level': 3
                    })

            # Level 4+ spells (with level in parentheses)
            level4plus_spells = request.form.get('spells_level_4', '').split('\n')
            for spell_entry in level4plus_spells:
                spell_entry = spell_entry.strip()
                if spell_entry:
                    # Try to extract the level from the format "Spell Name (Level X)"
                    level_match = re.search(r'\(Level (\d+)\)', spell_entry)
                    if level_match:
                        spell_level = int(level_match.group(1))
                        spell_name = spell_entry.split('(Level')[0].strip()
                    else:
                        spell_level = 4  # Default to level 4 if no level specified
                        spell_name = spell_entry

                    new_spells.append({
                        'name': spell_name,
                        'level': spell_level
                    })

            character['spellcasting']['spells'] = new_spells
        else:
            # For non-spellcasting characters, handle the simple spells list
            character['spells'] = request.form.get('spells', '').split('\n')

        save_character(character)
        flash('Character updated successfully!')
        return redirect(url_for('view_character', character_id=character_id))

    # Prepare spell lists and proficient skills before rendering the template
    spell_lists = prepare_spell_lists(character)
    proficient_skills = get_proficient_skill_names(character)

    return render_template('character_form.html', character=character,
                           spell_lists=spell_lists, proficient_skills=proficient_skills)


@app.route('/character/<character_id>/delete', methods=['POST'])
def delete_character(character_id):
    file_path = get_character_path(character_id)
    if os.path.exists(file_path):
        os.remove(file_path)
        flash('Character deleted successfully!')
    else:
        flash('Character not found!')
    return redirect(url_for('index'))


@app.route('/api/characters')
def api_characters():
    characters = load_characters()
    return jsonify(characters)


@app.route('/api/character/<character_id>')
def api_character(character_id):
    character = load_character(character_id)
    if character:
        return jsonify(character)
    return jsonify({'error': 'Character not found'}), 404


@app.route('/api/character/<character_id>/spellslots', methods=['POST'])
def update_spell_slots(character_id):
    """
    Update a character's spell slots usage
    """
    character = load_character(character_id)
    if not character:
        return jsonify({'error': 'Character not found'}), 404

    # Check if the character has spellcasting
    if 'spellcasting' not in character:
        return jsonify({'error': 'Character does not have spellcasting abilities'}), 400

    # Get the updated spell slot data
    data = request.json
    if not data or 'level' not in data or 'used' not in data:
        return jsonify({'error': 'Invalid data'}), 400

    level = str(data['level'])
    used = int(data['used'])

    # Validate the spell slot level
    if level not in character['spellcasting']['spell_slots']:
        return jsonify({'error': f'Invalid spell slot level: {level}'}), 400

    # Validate the usage count
    total_slots = character['spellcasting']['spell_slots'][level]['total']
    if used < 0 or used > total_slots:
        return jsonify({'error': f'Invalid usage count. Must be between 0 and {total_slots}'}), 400

    # Update the spell slot usage
    character['spellcasting']['spell_slots'][level]['used'] = used

    # Save the character
    save_character(character)

    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(debug=True)
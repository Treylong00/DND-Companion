from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
import json
import os
import re

app = Flask(__name__)
app.secret_key = 'dnd_secret_key'
app.config.update(
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    UPLOAD_FOLDER='uploads'
)

# Directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_character_path(character_id):
    return os.path.join(DATA_DIR, f'{character_id}.json')


def load_character(character_id=None):
    if character_id:
        try:
            with open(get_character_path(character_id)) as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    characters = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            try:
                with open(os.path.join(DATA_DIR, filename)) as file:
                    characters.append(json.load(file))
            except json.JSONDecodeError:
                continue
    return characters


def save_character(character_data):
    if not character_data.get('id'):
        character_data['id'] = datetime.now().strftime('%Y%m%d%H%M%S')

    with open(get_character_path(character_data['id']), 'w') as file:
        json.dump(character_data, file, indent=2)
    return character_data['id']


def prepare_spell_lists(character):
    if not character or 'spellcasting' not in character or 'spells' not in character['spellcasting']:
        return {level: '' for level in ['level1', 'level2', 'level3', 'level4plus']}

    spell_lists = {str(i): [] for i in range(1, 4)}
    spell_lists['4plus'] = []

    for spell in character['spellcasting']['spells']:
        level = spell['level']
        if level <= 3:
            spell_lists[str(level)].append(spell['name'])
        else:
            spell_lists['4plus'].append(f"{spell['name']} (Level {level})")

    return {
        'level1': '\n'.join(spell_lists['1']),
        'level2': '\n'.join(spell_lists['2']),
        'level3': '\n'.join(spell_lists['3']),
        'level4plus': '\n'.join(spell_lists['4plus'])
    }


def get_proficient_skill_names(character):
    if not character or 'skills' not in character:
        return []

    skills = character['skills']
    if not skills:
        return []

    if isinstance(skills[0], dict):
        return [skill['name'] for skill in skills if skill.get('proficient')]
    return skills


def process_spellcasting_data(character, form_data):
    if 'spellcasting' not in character:
        return character

    spellcasting = character['spellcasting']
    spellcasting['class'] = form_data.get('spellcasting_class', '')
    ability = form_data.get('spellcasting_ability', '')

    if ability:
        spellcasting['ability'] = ability
        ability_mod = character['ability_modifiers'][ability]
        spellcasting['spell_save_dc'] = 8 + character['proficiency_bonus'] + ability_mod
        spellcasting['spell_attack_bonus'] = character['proficiency_bonus'] + ability_mod

    spellcasting['cantrips'] = [c.strip() for c in form_data.get('cantrips', '').split('\n') if c.strip()]
    spellcasting['spells'] = []

    for level in range(1, 4):
        spells = form_data.get(f'spells_level_{level}', '').split('\n')
        spellcasting['spells'].extend({'name': s.strip(), 'level': level} for s in spells if s.strip())

    # Handle level 4+ spells
    for spell in form_data.get('spells_level_4', '').split('\n'):
        if not spell.strip():
            continue
        level_match = re.search(r'\(Level (\d+)\)', spell)
        level = int(level_match.group(1)) if level_match else 4
        name = spell.split('(Level')[0].strip() if level_match else spell.strip()
        spellcasting['spells'].append({'name': name, 'level': level})

    return character


# Routes
@app.route('/')
def index():
    return render_template('index.html', characters=load_character())


@app.route('/import', methods=['GET', 'POST'])
def import_character():
    if request.method == 'GET':
        return render_template('import.html')

    if 'pdf_file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['pdf_file']
    if not file or not file.filename:
        flash('No selected file')
        return redirect(request.url)

    if not file.filename.lower().endswith('.pdf'):
        flash('Only PDF files are allowed')
        return redirect(request.url)

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        file.save(file_path)
        character_id = None
        error = None

        try:
            from pdf_import import import_character_from_pdf
            character_id, error = import_character_from_pdf(file_path, DATA_DIR)

            if error and "No fillable form fields found" in error:
                flash('No fillable form fields found. Attempting OCR import...')
                from ocr_support import import_character_from_scanned_pdf
                character_id, error = import_character_from_scanned_pdf(file_path, DATA_DIR)
        except ImportError:
            flash('Standard PDF import failed. Attempting OCR import...')
            from ocr_support import import_character_from_scanned_pdf
            character_id, error = import_character_from_scanned_pdf(file_path, DATA_DIR)

        if error:
            flash(f'Error importing character: {error}')
            return redirect(url_for('import_character'))

        flash('Character imported successfully!')
        return redirect(url_for('view_character', character_id=character_id))

    except Exception as e:
        flash(f'Error processing file: {str(e)}')
        return redirect(url_for('import_character'))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.route('/character/new', methods=['GET', 'POST'])
def new_character():
    if request.method == 'GET':
        return render_template('character_form.html', character=None)

    character_data = {
        'name': request.form.get('name', 'Unnamed Character'),
        'race': request.form.get('race', ''),
        'class': request.form.get('class', ''),
        'level': int(request.form.get('level', 1)),
        'abilities': {
            ability: int(request.form.get(ability, 10))
            for ability in ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']
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


@app.route('/character/<character_id>')
def view_character(character_id):
    character = load_character(character_id)
    if not character:
        flash('Character not found!')
        return redirect(url_for('index'))
    return render_template('character.html', character=character)


@app.route('/character/<character_id>/edit', methods=['GET', 'POST'])
def edit_character(character_id):
    character = load_character(character_id)
    if not character:
        flash('Character not found!')
        return redirect(url_for('index'))

    if request.method == 'GET':
        spell_lists = prepare_spell_lists(character)
        proficient_skills = get_proficient_skill_names(character)
        return render_template('character_form.html',
                               character=character,
                               spell_lists=spell_lists,
                               proficient_skills=proficient_skills)

    character.update({
        'name': request.form.get('name', character['name']),
        'race': request.form.get('race', character['race']),
        'class': request.form.get('class', character['class']),
        'level': int(request.form.get('level', character['level'])),
        'abilities': {
            ability: int(request.form.get(ability, character['abilities'][ability]))
            for ability in character['abilities']
        },
        'hp': {
            'max': int(request.form.get('max_hp', character['hp']['max'])),
            'current': int(request.form.get('current_hp', character['hp']['current']))
        },
        'armor_class': int(request.form.get('armor_class', character['armor_class'])),
        'proficiency_bonus': int(request.form.get('proficiency_bonus', character['proficiency_bonus'])),
        'skills': request.form.getlist('skills'),
        'equipment': request.form.get('equipment', '').split('\n'),
        'background': request.form.get('background', ''),
        'traits': request.form.get('traits', '')
    })

    character = process_spellcasting_data(character, request.form)
    save_character(character)
    flash('Character updated successfully!')
    return redirect(url_for('view_character', character_id=character_id))


@app.route('/character/<character_id>/delete', methods=['POST'])
def delete_character(character_id):
    try:
        os.remove(get_character_path(character_id))
        flash('Character deleted successfully!')
    except FileNotFoundError:
        flash('Character not found!')
    return redirect(url_for('index'))


@app.route('/api/characters')
def api_characters():
    return jsonify(load_character())


@app.route('/api/character/<character_id>')
def api_character(character_id):
    character = load_character(character_id)
    if not character:
        return jsonify({'error': 'Character not found'}), 404
    return jsonify(character)


@app.route('/api/character/<character_id>/spellslots', methods=['POST'])
def update_spell_slots(character_id):
    character = load_character(character_id)
    if not character:
        return jsonify({'error': 'Character not found'}), 404

    if 'spellcasting' not in character:
        return jsonify({'error': 'Character does not have spellcasting abilities'}), 400

    data = request.json
    if not data or 'level' not in data or 'used' not in data:
        return jsonify({'error': 'Invalid data'}), 400

    level = str(data['level'])
    used = int(data['used'])

    spell_slots = character['spellcasting']['spell_slots']
    if level not in spell_slots:
        return jsonify({'error': f'Invalid spell slot level: {level}'}), 400

    total_slots = spell_slots[level]['total']
    if not 0 <= used <= total_slots:
        return jsonify({'error': f'Invalid usage count. Must be between 0 and {total_slots}'}), 400

    spell_slots[level]['used'] = used
    save_character(character)
    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(debug=True)
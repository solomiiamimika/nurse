"""
Auto-translation helper for Flask-Babel .po files.

Usage:
    python translate.py          # translate all empty msgstr entries
    python translate.py --full   # also re-extract strings from templates + update .po first

Requires:
    pip install deep-translator

How it works:
  1. (optional) pybabel extract + update to pick up new strings
  2. Read translations/uk/LC_MESSAGES/messages.po
  3. Translate every empty msgstr from English → Ukrainian via Google Translate (free)
  4. Write the translated .po file back
  5. pybabel compile → generates messages.mo
"""

import re
import os
import sys
import subprocess
import io

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PO_FILE = os.path.join('translations', 'uk', 'LC_MESSAGES', 'messages.po')
BABEL_CFG = 'babel.cfg'
POT_FILE = 'messages.pot'
SRC_LANG = 'en'
DST_LANG = 'uk'


def run(cmd):
    print(f'  $ {cmd}')
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f'  [!] Command failed: {cmd}')
        sys.exit(1)


def extract_and_update():
    print('\n[1] Extracting strings from source...')
    run(f'pybabel extract -F {BABEL_CFG} -k _l -o {POT_FILE} .')
    print('\n[2] Updating .po file with new strings...')
    run(f'pybabel update -i {POT_FILE} -d translations')
    os.remove(POT_FILE)


def translate_po():
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print('\n[!] deep-translator not installed. Run: pip install deep-translator')
        sys.exit(1)

    translator = GoogleTranslator(source=SRC_LANG, target=DST_LANG)

    with open(PO_FILE, encoding='utf-8') as f:
        content = f.read()

    # Split into entries
    entries = re.split(r'\n(?=(?:#|msgid))', content)

    translated_count = 0
    output_entries = []

    for entry in entries:
        # Find msgid and msgstr pairs
        msgid_match = re.search(r'^msgid\s+"(.*?)"(?:\n".*?")*', entry, re.MULTILINE)
        msgstr_match = re.search(r'^msgstr\s+"(.*?)"(?:\n".*?")*', entry, re.MULTILINE)

        if msgid_match and msgstr_match:
            # Extract full msgid value (handle multiline strings)
            msgid_lines = re.findall(r'^(?:msgid|(?<=\n))\s*"(.*?)"', entry, re.MULTILINE)
            msgid_value = ''.join(msgid_lines).replace('\\n', '\n')

            # Extract msgstr value
            msgstr_block = msgstr_match.group(0)
            msgstr_lines = re.findall(r'"(.*?)"', msgstr_block)
            msgstr_value = ''.join(msgstr_lines)

            # Translate only if msgstr is empty and msgid is not empty
            if msgid_value.strip() and not msgstr_value.strip():
                try:
                    translated = translator.translate(msgid_value)
                    if translated:
                        # Escape for .po format
                        escaped = translated.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                        new_msgstr = f'msgstr "{escaped}"'
                        entry = entry[:msgstr_match.start()] + new_msgstr + entry[msgstr_match.end():]
                        translated_count += 1
                        print(f'  + "{msgid_value[:50]}" -> "{translated[:50]}"')
                except Exception as e:
                    print(f'  [!] Failed to translate "{msgid_value[:40]}": {e}')

        output_entries.append(entry)

    new_content = '\n'.join(output_entries)
    with open(PO_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'\n  Translated {translated_count} new strings.')
    return translated_count


def compile_po():
    print('\n[4] Compiling .po -> .mo...')
    run('pybabel compile -d translations')


if __name__ == '__main__':
    full = '--full' in sys.argv

    if full:
        extract_and_update()

    print('\n[3] Translating empty entries...')
    count = translate_po()

    if count > 0 or full:
        compile_po()
        print('\nOK Done! Restart Flask to see changes.')
    else:
        print('\nOK Nothing to translate. All entries already filled.')

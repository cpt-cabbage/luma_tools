Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe -c @"
import sys
from core.design_tokens import render_qss, token_map
from core.config import CUSTOM_STYLE_PATH, UIColors, UIStyles

tokens = token_map()
print(f'tokens defined: {len(tokens)}')

with open(CUSTOM_STYLE_PATH, encoding='utf-8') as fh:
    template = fh.read()

try:
    qss = render_qss(template)
except KeyError as e:
    print('FAIL:', e)
    sys.exit(1)

import re
left = re.findall(r'\{\{[^}]+\}\}', qss)
print(f'unresolved placeholders: {len(left)}')
if left:
    print(sorted(set(left)))
    sys.exit(1)

print(f'rendered qss: {len(qss)} chars, {qss.count(chr(10))} lines')
print(f'!important count: {qss.count(\"!important\")}')
print(f'UIColors.BG_DARK -> {UIColors.BG_DARK}')
print(f'UIColors.ACCENT_BLUE -> {UIColors.ACCENT_BLUE}')
print('UIStyles.BUTTON_PRIMARY renders:', 'background-color: #5aa9ff' in UIStyles.BUTTON_PRIMARY)
print('OK')
"@

Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe python\core\luma_tools.py Solensia sh0030 lighting 'W:\Solensia\shots\sh0030\work\lighting' 'christophe.leyder' 'combined' --tab mp4maker --auto-close 30

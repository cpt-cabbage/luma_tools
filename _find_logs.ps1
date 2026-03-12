Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' -Filter '*christophe*' | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object { $_.FullName }


import os

path = r'd:\Ares Engine\app\services\writer_service.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

lines[21] = '        prompt_path = Path(__file__).parent / "prompts" / "writer.md"\n'

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed line 22")

import re

with open('docs/maqueta_interactiva_de_interfaz.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Let's search for id="tab-..." elements in any tag
pattern = r'(<([a-zA-Z0-9]+)[^>]*id="tab-([^"]+)"[^>]*>)'
matches = list(re.finditer(pattern, content))

print(f"Found {len(matches)} matches.")

for i, match in enumerate(matches):
    start_pos = match.start()
    tag_open = match.group(1)
    tag_name = match.group(2)
    tab_name = match.group(3)
    
    # find matching closing tag (by counting tag_name tags)
    pos = match.end()
    count = 1
    while count > 0 and pos < len(content):
        next_open = content.find(f'<{tag_name}', pos)
        next_close = content.find(f'</{tag_name}>', pos)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            count += 1
            pos = next_open + len(tag_name) + 1
        else:
            count -= 1
            pos = next_close + len(tag_name) + 3
    end_pos = pos
    print(f"Tab: {tab_name} ({tag_name}) starts at {start_pos} and ends at {end_pos}. Length: {end_pos - start_pos} chars.")
    # save to a scratch file
    with open(f"scratch/tab_{tab_name}.html", "w", encoding="utf-8") as out:
        out.write(content[start_pos:end_pos])

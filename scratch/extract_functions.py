import re

with open('docs/maqueta_interactiva_de_interfaz.html', 'r', encoding='utf-8') as f:
    content = f.read()

scripts = re.findall(r'<script>([\s\S]*?)</script>', content)
script_content = scripts[1] if len(scripts) > 1 else ""

keywords = ['toggleTheme', 'switchTab', 'updateRates', 'bcv', 'factor', 'tasa', 'theme']
results = []

for line in script_content.splitlines():
    for kw in keywords:
        if kw in line:
            results.append(line.strip())
            break

with open('scratch/script_matches.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(results[:200]))

# Let's extract specific function definitions
def extract_func(name):
    # find function name(...) {
    idx = script_content.find(f"function {name}")
    if idx == -1:
        # try arrow function
        idx = script_content.find(f"const {name}")
    if idx == -1:
        return f"Function {name} not found"
    
    # find outer curly braces
    pos = script_content.find("{", idx)
    if pos == -1:
        return f"Opening brace for {name} not found"
    
    count = 1
    pos += 1
    while count > 0 and pos < len(script_content):
        if script_content[pos] == "{":
            count += 1
        elif script_content[pos] == "}":
            count -= 1
        pos += 1
    return script_content[idx:pos]

functions = ['toggleTheme', 'switchTab', 'updateRates', 'simulateSync']
with open('scratch/extracted_functions.js', 'w', encoding='utf-8') as f:
    for func in functions:
        f.write(f"// --- {func} ---\n")
        f.write(extract_func(func))
        f.write("\n\n")

print("Extracted successfully.")

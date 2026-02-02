import os
import shutil
import subprocess

# CONFIGURACIÓN
TARGET_EXTENSIONS = ['.py', '.js', '.html', '.css', '.java', '.json', '.lua', '.yml']
MIN_LINES_PER_PART = 500
IGNORE_DIRS = ['.git', '.github', '__pycache__', 'node_modules']

def is_safe_break_point(line, extension):
    stripped = line.strip()
    if not stripped: return False

    # Lógica PYTHON: Romper ANTES de definir una nueva función/clase
    if extension == 'py':
        if not line.startswith(' ') and not line.startswith('\t'):
            if line.startswith('@') or line.startswith('#') or line.startswith('//'): 
                return False
            return 'BEFORE' # Indica cortar antes de esta línea
    
    # Lógica HTML: Romper DESPUÉS de cerrar un bloque importante
    elif extension in ['html', 'xml', 'htm']:
        if stripped.endswith('</div>') or stripped.endswith('</section>') or \
           stripped.endswith('</body>') or stripped.endswith('</script>') or \
           stripped.endswith('</style>'):
            return 'AFTER' # Indica cortar después de esta línea

    # Lógica C-STYLE (JS, CSS, Java, etc): Romper DESPUÉS de cerrar llave
    elif extension in ['js', 'css', 'java', 'json', 'lua']:
        if stripped.endswith('}'):
            return 'AFTER'
            
    return False

def get_changed_files():
    """
    Pregunta a GIT qué archivos cambiaron entre el commit anterior y el actual.
    """
    try:
        cmd = ["git", "diff", "--name-only", "HEAD~1", "HEAD"]
        output = subprocess.check_output(cmd, text=True)
        files = output.splitlines()
        
        valid_files = []
        for f in files:
            if os.path.exists(f):
                _, ext = os.path.splitext(f)
                if ext in TARGET_EXTENSIONS and f != 'autosplit.py':
                    valid_files.append(f)
        return valid_files
    except Exception as e:
        print(f"Error obteniendo cambios de git: {e}")
        return []

def split_file(file_path):
    file_name = os.path.basename(file_path)
    print(f"Detectado cambio en: {file_name} -> Procesando...")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        return

    if len(lines) <= MIN_LINES_PER_PART:
        print(f"  -> Omitido (Muy corto: {len(lines)} líneas)")
        return

    base_name = os.path.splitext(file_name)[0]
    extension = os.path.splitext(file_name)[1].replace('.', '')
    output_dir_name = f"{base_name}_{extension}_partes"
    output_dir = os.path.join(os.path.dirname(file_path), output_dir_name)

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    parts = []
    current_chunk = []
    
    for line in lines:
        break_type = is_safe_break_point(line, extension)
        
        # Solo intentamos cortar si ya superamos el mínimo de líneas
        if len(current_chunk) >= MIN_LINES_PER_PART:
            
            if break_type == 'BEFORE':
                parts.append(current_chunk)
                current_chunk = [line]
                continue
                
            elif break_type == 'AFTER':
                current_chunk.append(line)
                parts.append(current_chunk)
                current_chunk = []
                continue

        current_chunk.append(line)

    if current_chunk:
        parts.append(current_chunk)

    total_parts = len(parts)
    for i, chunk in enumerate(parts):
        part_filename = f"{base_name}_parte_{i+1}.{extension}"
        part_path = os.path.join(output_dir, part_filename)
        
        # Generar cabecera según el lenguaje
        header_text = f"// PARTE {i+1}/{total_parts} - {file_name}\n// CAMBIOS RECIENTES\n\n"
        
        if extension == 'py': 
            header_text = header_text.replace('//', '#')
        elif extension in ['html', 'xml', 'htm']: 
            header_text = f"\n\n\n"
        elif extension == 'lua':
            header_text = header_text.replace('//', '--')

        with open(part_path, 'w', encoding='utf-8') as p:
            p.write(header_text)
            p.writelines(chunk)

def main():
    print("Buscando archivos modificados en el último commit...")
    changed_files = get_changed_files()
    
    if not changed_files:
        print("No se detectaron archivos de código modificados.")
    
    for file in changed_files:
        split_file(file)

if __name__ == "__main__":
    main()

import os
import shutil
import re

# CONFIGURACIÓN
TARGET_EXTENSIONS = ['.py', '.js', '.html', '.css', '.java', '.json', '.lua', '.yml']
MIN_LINES_PER_PART = 500  # Mínimo de líneas antes de buscar un punto de corte
IGNORE_DIRS = ['.git', '.github', '__pycache__', 'node_modules']

def is_safe_break_point(line, extension):
    """
    Determina si es seguro cortar antes de esta línea.
    Busca líneas que comiencen en la columna 0 (sin espacios al inicio),
    lo que usualmente indica una nueva definición global.
    """
    # Si la línea está vacía, no es un buen punto de referencia, seguimos buscando
    if not line.strip():
        return False

    # Lógica: Si la línea NO empieza con espacio o tabulación, es nivel raíz.
    # Esto funciona para Python (def, class), JS (function, const), CSS (selectores), etc.
    if not line.startswith(' ') and not line.startswith('\t'):
        
        # Opcional: Evitar cortar justo en decoradores de Python o comentarios sueltos
        if line.startswith('@') or line.startswith('#') or line.startswith('//'):
            return False
            
        return True
    
    return False

def split_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        print(f"Saltando archivo binario: {file_path}")
        return

    # Si es pequeño, no hacemos nada
    if len(lines) <= MIN_LINES_PER_PART:
        return

    file_name = os.path.basename(file_path)
    base_name = os.path.splitext(file_name)[0]
    extension = os.path.splitext(file_name)[1].replace('.', '')
    output_dir_name = f"{base_name}_{extension}_partes"
    output_dir = os.path.join(os.path.dirname(file_path), output_dir_name)

    # Limpieza
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    print(f"Procesando: {file_name} (Inteligente)...")

    parts = []
    current_chunk = []
    
    for line in lines:
        current_chunk.append(line)
        
        # Solo intentamos cortar si ya tenemos suficientes líneas
        if len(current_chunk) >= MIN_LINES_PER_PART:
            # Y si encontramos un punto seguro (inicio de nueva función/clase)
            if is_safe_break_point(line, extension):
                # El "line" actual pertenece a la SIGUIENTE parte, así que lo sacamos
                last_line = current_chunk.pop() 
                parts.append(current_chunk)
                current_chunk = [last_line] # Iniciamos el nuevo chunk con esta línea

    # Añadir lo que sobró al final
    if current_chunk:
        parts.append(current_chunk)

    # Escribir los archivos
    total_parts = len(parts)
    for i, chunk in enumerate(parts):
        part_filename = f"{base_name}_parte_{i+1}.{extension}"
        part_path = os.path.join(output_dir, part_filename)
        
        # Cabecera informativa para la IA
        header_text = (
            f"// PARTE {i+1} DE {total_parts} DEL ARCHIVO: {file_name}\n"
            f"// CONTINUACIÓN AUTOMÁTICA. EL CONTEXTO ANTERIOR ES NECESARIO.\n\n"
        )
        if extension == 'py': # Ajuste de comentarios para Python
            header_text = header_text.replace('//', '#')
        elif extension in ['html', 'xml']:
            header_text = f"\n"

        with open(part_path, 'w', encoding='utf-8') as p:
            p.write(header_text)
            p.writelines(chunk)

def main():
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.endswith('_partes')]
        
        for file in files:
            name, ext = os.path.splitext(file)
            if ext in TARGET_EXTENSIONS and file != 'autosplit.py':
                split_file(os.path.join(root, file))

if __name__ == "__main__":
    main()

"""Collect the license texts for bundled dependencies."""
from importlib import metadata
from pathlib import Path

output = []
for name in ('cryptography', 'cffi', 'pycparser', 'pillow'):
    distribution = metadata.distribution(name)
    output.append(f'===== {name} {distribution.version} =====\n')
    paths = [item for item in distribution.files or [] if '.dist-info/' in str(item).replace('\\', '/') and 'license' in str(item).lower() and Path(item).name.lower().startswith(('license', 'copying'))]
    if not paths:
        raise RuntimeError(f'No license file found for {name}')
    for item in paths:
        output.append(f'--- {Path(item).name} ---\n')
        output.append(distribution.locate_file(item).read_text(encoding='utf-8') + '\n')
Path('dist').mkdir(exist_ok=True)
Path('dist/DEPENDENCY-LICENSES.txt').write_text('\n'.join(output), encoding='utf-8')

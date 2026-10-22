"""Render the paper's editable figures for both website themes.

Usage: python tools/render_asic_figures.py /path/to/disposable-build-directory
The paper sources retain their labels; n237 is applied only to website exports.
"""
import pathlib
import re
import subprocess
import sys

SITE = pathlib.Path(__file__).resolve().parent.parent
SOURCE = SITE / 'asic-puzzle/source/figures'
OUTPUT = SITE / 'assets/asic-puzzle/fig'
DARK = {
    '172033': 'E3EBF7', '5B6472': 'A6B8CF', '3157A4': '93B9FF',
    '0A7D33': '64D39B', '7B52C4': 'BC9CF2', 'B9C0CC': '526780',
    'F1F4F8': '25364B', 'EEF3FC': '1B304C', 'FFFFFF': '101D30',
    'EEF1F5': '25364B', 'C6CDD7': '41546E', '8A93A3': '60748C',
    'F0E5C3': '403D31', 'E1CC88': '706348', 'E4D093': '706348',
}


def main():
    build = pathlib.Path(sys.argv[1]).resolve()
    for theme in ('light', 'dark'):
        work = build / theme
        work.mkdir(parents=True, exist_ok=True)
        for path in SOURCE.iterdir():
            if path.suffix not in ('.tex', '.tikz'):
                continue
            text = re.sub(r'\bn7\b', 'n237', path.read_text())
            if theme == 'dark':
                text = re.sub(r'\{([A-Fa-f0-9]{6})\}', lambda m: '{' + DARK.get(m[1].upper(), m[1]) + '}', text)
                if path.name in ('recovered-board.tikz', 'recovered-input-grid.tikz'):
                    text = text.replace('{526780}', '{71849C}')
                text = re.sub(r'(fig[a-z]+!\d+)(?![\d!])', r'\1!figpaper', text)
                if path.name == 'figstyle.tex':
                    text += '\n\\definecolor{figpaper}{HTML}{101D30}\n\\definecolor{white}{HTML}{101D30}\n\\definecolor{black}{HTML}{E3EBF7}\n'
            (work / path.name).write_text(text)
        suffix = '-dark' if theme == 'dark' else ''
        for source in sorted(SOURCE.glob('*.tikz')):
            name = source.stem
            result = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', f'{name}.tex'], cwd=work, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stdout[-5000:])
            subprocess.run(['pdftocairo', '-svg', str(work / f'{name}.pdf'), str(OUTPUT / f'{name}{suffix}.svg')], check=True)
            print(theme, name, flush=True)
        net = re.sub(r'\bn7\b', 'n237', (SOURCE / 'warmup-net-example.svg').read_text())
        net = net.replace('<rect width="100%" height="100%" fill="#FFFFFF"/>', '')
        if theme == 'dark':
            net = re.sub(r'#([A-Fa-f0-9]{6})', lambda m: '#' + DARK.get(m[1].upper(), m[1]), net)
        else:
            net = net.replace('fill="#FFFFFF"', 'fill="#F6F9FD"')
        (OUTPUT / f'warmup-net-example{suffix}.svg').write_text(net)


if __name__ == '__main__':
    main()

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

root = Path(__file__).parent
font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 44)
header = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 55)

def page(title, lines):
    image = Image.new('RGB', (1200, 1600), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((75, 100), title, fill='black', font=header)
    for i, line in enumerate(lines):
        draw.text((75, 250 + i * 95), line, fill='black', font=font)
    return image

first = page('SCANNED FIELD NOTES - PAGE ONE', [
    'The eastern trail has seven lanterns.',
    'The north gate opens at sunrise.',
    'This page is raster-only for OCR testing.',
    'The marked route crosses a quiet meadow.',
    'The field team counted each item twice.',
    'The written log belongs to the archive.',
    'The river bridge is beside the old station.',
    'The map is stored with the field notes.',
    'The morning survey had clear weather.',
    'The final count was checked by the guide.',
])
second = page('ROTATED FIELD NOTES - PAGE TWO', [
    'The western trail has nine compasses.',
    'The south gate opens at sunset.',
    'This page is sideways for rotation testing.',
    'The marked route crosses a narrow valley.',
    'The field team counted each item twice.',
    'The written log belongs to the archive.',
    'The stone bridge is beside the west station.',
    'The map is stored with the field notes.',
    'The evening survey had clear weather.',
    'The final count was checked by the guide.',
]).rotate(90, expand=False, fillcolor='white')
first.save(root / 'scanned-rotated.pdf', 'PDF', resolution=150, save_all=True, append_images=[second])

(root / 'quality-warning.txt').write_text(
    ('The route guide and the archive map describe the seven lanterns clearly. ' * 8)
    + 'One replacement marker appears at the end: \ufffd.\n', encoding='utf-8'
)
(root / 'quality-language-fr.txt').write_text(
    'Le guide de la route et la carte de la ville sont pour la marche avec le groupe.\n'
    'Le guide et la carte de la ville sont pour la marche avec le groupe.\n', encoding='utf-8'
)
(root / 'quality-language-mixed.txt').write_text(
    'The guide and the map are for the route.\n'
    'Маршрут и карта находятся рядом с восточными воротами.\n', encoding='utf-8'
)

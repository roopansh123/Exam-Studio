import os
import sys
import sqlite3
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def create_lk_logo(size=1024):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    margin = int(size * 0.045)
    r = int(size * 0.22)
    box = [margin, margin, size - margin, size - margin]

    # Royal blue gradient
    grad = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for y in range(size):
        ratio = y / float(size)
        r_c = int(37 * (1 - ratio) + 15 * ratio)
        g_c = int(99 * (1 - ratio) + 23 * ratio)
        b_c = int(235 * (1 - ratio) + 68 * ratio)
        gdraw.line([(0, y), (size, y)], fill=(r_c, g_c, b_c, 255))

    # Squircle mask
    mask = Image.new('L', (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle(box, radius=r, fill=255)
    img.paste(grad, (0, 0), mask)

    # Borders
    bdraw = ImageDraw.Draw(img)
    bdraw.rounded_rectangle(box, radius=r, outline=(255, 255, 255, 80), width=int(size * 0.012))
    inner_box = [margin + int(size * 0.015), margin + int(size * 0.015), size - margin - int(size * 0.015), size - margin - int(size * 0.015)]
    bdraw.rounded_rectangle(inner_box, radius=r - int(size * 0.015), outline=(96, 165, 250, 100), width=int(size * 0.008))

    # Bold LK font
    font_path = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
    if not os.path.exists(font_path):
        font_path = '/System/Library/Fonts/HelveticaNeue.ttc'

    try:
        font = ImageFont.truetype(font_path, int(size * 0.52))
    except Exception:
        font = ImageFont.load_default()

    text = 'LK'
    bbox = bdraw.textbbox((0, 0), text, font=font)
    t_w = bbox[2] - bbox[0]
    t_h = bbox[3] - bbox[1]
    pos_x = (size - t_w) // 2 - bbox[0]
    pos_y = (size - t_h) // 2 - bbox[1]

    # Shadow
    shadow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.text((pos_x, pos_y + int(size * 0.02)), text, font=font, fill=(10, 15, 40, 200))
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(size * 0.018)))
    img = Image.alpha_composite(img, shadow)

    # Text
    tdraw = ImageDraw.Draw(img)
    tdraw.text((pos_x, pos_y), text, font=font, fill=(255, 255, 255, 255))
    return img

def main():
    icon_1024 = create_lk_logo(1024)
    icon_1024.save('app_icon.png')

    # Windows ICO
    ico_sizes = [(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)]
    icon_1024.save('app_icon.ico', format='ICO', sizes=ico_sizes)

    # macOS ICNS
    if sys.platform == 'darwin':
        iconset_dir = 'app_icon.iconset'
        os.makedirs(iconset_dir, exist_ok=True)
        sizes = [
            (16, 'icon_16x16.png'), (32, 'icon_16x16@2x.png'),
            (32, 'icon_32x32.png'), (64, 'icon_32x32@2x.png'),
            (128, 'icon_128x128.png'), (256, 'icon_128x128@2x.png'),
            (256, 'icon_256x256.png'), (512, 'icon_256x256@2x.png'),
            (512, 'icon_512x512.png'), (1024, 'icon_512x512@2x.png'),
        ]
        for s, name in sizes:
            icon_1024.resize((s, s), Image.Resampling.LANCZOS).save(os.path.join(iconset_dir, name))
        try:
            subprocess.run(['iconutil', '-c', 'icns', iconset_dir, '-o', 'app_icon.icns'], check=True)
        except Exception as e:
            print('iconutil error:', e)

    # School logo files
    os.makedirs('uploads/logos', exist_ok=True)
    icon_512 = icon_1024.resize((512, 512), Image.Resampling.LANCZOS)
    logo_png = 'uploads/logos/school_logo.png'
    logo_jpg = 'uploads/logos/school_logo.JPG'
    icon_512.save(logo_png)
    icon_512.convert('RGB').save(logo_jpg, quality=95)

    # Update database
    for db in ['question_paper.db']:
        if os.path.exists(db):
            conn = sqlite3.connect(db)
            conn.execute("UPDATE school_settings SET logo_path = ? WHERE id = 1", (logo_png,))
            conn.commit()
            conn.close()
    print('LK logo and application icons generated successfully!')

if __name__ == '__main__':
    main()

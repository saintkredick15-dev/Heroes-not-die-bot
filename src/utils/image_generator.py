import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageChops

# Конфігурація шляхів
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
DEFAULT_BG_COLOR = (26, 26, 46) # #1A1A2E (Темно-синій фон, короче за замовчуванням чисто такий)
def get_available_fonts() -> list[str]:
    if not os.path.exists(FONTS_DIR):
        return []
    
    fonts = []
    for f in os.listdir(FONTS_DIR):
        if f.lower().endswith(('.ttf', '.otf')):
            # Відрізаємо розширення для гарної назви
            name = os.path.splitext(f)[0]
            fonts.append(name)
    return sorted(fonts)

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return (255, 255, 255) # білий за замовчуванням
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)

def create_circular_mask(size: tuple[int, int]) -> Image.Image:
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    return mask

def generate_welcome_card(
    avatar_bytes: bytes,
    username: str,
    top_text: str = "ЛАСКАВО ПРОСИМО",
    bg_bytes: bytes | None = None,
    bg_color_hex: str = "#1A1A2E",
    font_name: str = "ARIAL",
    font_color_hex: str = "#FFFFFF",
    avatar_outline_color_hex: str = "#5865F2"
) -> BytesIO:
    base_width, base_height = 800, 300
    bg_color_rgb = hex_to_rgb(bg_color_hex)
    
    if bg_bytes:
        try:
            bg_image = Image.open(BytesIO(bg_bytes)).convert("RGBA")
            bg_image = bg_image.resize((base_width, base_height), Image.Resampling.LANCZOS)
            base = bg_image
        except Exception:
            base = Image.new("RGBA", (base_width, base_height), bg_color_rgb)
    else:
        base = Image.new("RGBA", (base_width, base_height), bg_color_rgb)

    avatar_size = (150, 150)
    try:
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize(avatar_size, Image.Resampling.LANCZOS)
        
        mask = create_circular_mask(avatar_size)
        circular_avatar = Image.new("RGBA", avatar_size, (0,0,0,0))
        circular_avatar.paste(avatar, (0,0), mask)
        
        avatar_x = (base_width - avatar_size[0]) // 2
        avatar_y = 30
        
        outline_size = (avatar_size[0] + 16, avatar_size[1] + 16)
        outline_bg = Image.new("RGBA", outline_size, (0,0,0,0))
        draw_outline = ImageDraw.Draw(outline_bg)
        
        outline_rgb = hex_to_rgb(avatar_outline_color_hex)
        draw_outline.ellipse((0, 0) + outline_size, fill=outline_rgb)
        
        outline_x = avatar_x - 8
        outline_y = avatar_y - 8
        
        base.paste(outline_bg, (outline_x, outline_y), outline_bg)
        base.paste(circular_avatar, (avatar_x, avatar_y), circular_avatar)
        
    except Exception as e:
        print(f"[Image Generator] Помилка обробки аватара: {e}")

    draw = ImageDraw.Draw(base)
    rgb_color = hex_to_rgb(font_color_hex)
    
    font_path = None
    for f in os.listdir(FONTS_DIR):
        if os.path.splitext(f)[0].lower() == font_name.lower():
            font_path = os.path.join(FONTS_DIR, f)
            break
            
    if font_path:
        try:
            top_font = ImageFont.truetype(font_path, 50)
            bot_font = ImageFont.truetype(font_path, 35)
        except:
            top_font = ImageFont.load_default()
            bot_font = ImageFont.load_default()
    else:
        top_font = ImageFont.load_default()
        bot_font = ImageFont.load_default()

    bbox_top = draw.textbbox((0, 0), top_text, font=top_font)
    top_w = bbox_top[2] - bbox_top[0]
    top_h = bbox_top[3] - bbox_top[1]
    
    top_x = (base_width - top_w) / 2
    top_y = 195
    draw.text((top_x, top_y), top_text, font=top_font, fill=rgb_color)
    
    bbox_bot = draw.textbbox((0, 0), username, font=bot_font)
    bot_w = bbox_bot[2] - bbox_bot[0]
    bot_y = top_y + top_h + 10
    bot_x = (base_width - bot_w) / 2
    
    draw.text((bot_x, bot_y), username, font=bot_font, fill=rgb_color)

    final_buffer = BytesIO()
    base.save(final_buffer, format="PNG")
    final_buffer.seek(0)
    
    return final_buffer

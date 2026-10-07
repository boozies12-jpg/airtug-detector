import os
import sys
import struct
import zlib
import subprocess

def create_png_radar_v2(width=48, height=48):
    """
    Generate a distinct 48x48 PNG with a vibrant violet/emerald v2 theme.
    Violet base (#7C3AED) with glowing emerald rings (#10B981) and radar beam.
    """
    pixels = bytearray(width * height * 4)
    cx, cy = width / 2.0, height / 2.0
    r_max = width / 2.0 - 2.0

    for y in range(height):
        for x in range(width):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            idx = (y * width + x) * 4

            if dist <= r_max:
                alpha = 255
                if dist > r_max - 1.0:
                    alpha = int(255 * (r_max - dist))

                # Radar rings & center target
                is_ring1 = abs(dist - 15) < 1.4
                is_ring2 = abs(dist - 9.5) < 1.4
                is_center = dist < 4.0
                # Radar sweep beam
                is_beam = (dx >= 0 and dy <= 0 and abs(dx - (-dy)) < 1.8)

                if is_center or is_ring1 or is_ring2:
                    # Glowing emerald (#10B981 -> RGB 16, 185, 129)
                    pixels[idx] = 16
                    pixels[idx + 1] = 185
                    pixels[idx + 2] = 129
                    pixels[idx + 3] = alpha
                elif is_beam:
                    # Bright mint beam (#A7F3D0)
                    pixels[idx] = 167
                    pixels[idx + 1] = 243
                    pixels[idx + 2] = 208
                    pixels[idx + 3] = alpha
                else:
                    # Vibrant violet background (#7C3AED -> RGB 124, 58, 237)
                    pixels[idx] = 124
                    pixels[idx + 1] = 58
                    pixels[idx + 2] = 237
                    pixels[idx + 3] = alpha
            else:
                pixels[idx] = 0
                pixels[idx + 1] = 0
                pixels[idx + 2] = 0
                pixels[idx + 3] = 0

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_scanlines = bytearray()
    for y in range(height):
        raw_scanlines.append(0)
        raw_scanlines.extend(pixels[y * width * 4:(y + 1) * width * 4])

    idat = zlib.compress(bytes(raw_scanlines), 9)
    png_bytes = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    return png_bytes

def create_ico_v2(ico_path):
    png_data = create_png_radar_v2(48, 48)
    header = struct.pack("<HHH", 0, 1, 1)
    dir_entry = struct.pack("<BBBBHHII", 48, 48, 0, 0, 1, 32, len(png_data), 6 + 16)
    with open(ico_path, "wb") as f:
        f.write(header)
        f.write(dir_entry)
        f.write(png_data)
    print(f"Created v2 icon at: {ico_path}")

def create_v2_shortcut():
    project_dir = os.path.abspath(os.path.dirname(__file__))
    desktop_path = os.path.expanduser("~/Desktop")

    ico_path = os.path.join(project_dir, "app_icon_v2.ico")
    create_ico_v2(ico_path)

    bat_path = os.path.join(project_dir, "start_windows.bat")
    lnk_path = os.path.join(desktop_path, "BLE Tracker Search v2.lnk")

    ps_cmd = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{lnk_path}')
$s.TargetPath = '{bat_path}'
$s.WorkingDirectory = '{project_dir}'
$s.Description = 'Windows BLE Tracker Search v2.0 - Security Pilot'
$s.IconLocation = '{ico_path},0'
$s.Save()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)
    print(f"Created v2 shortcut at: {lnk_path}")

if __name__ == "__main__":
    create_v2_shortcut()

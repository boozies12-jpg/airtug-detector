import os
import sys
import struct
import zlib

def create_png_radar(width=48, height=48):
    """Generate a clean 48x48 PNG with a blue circular radar / antenna design."""
    # Build raw RGBA image
    pixels = bytearray(width * height * 4)
    cx, cy = width / 2.0, height / 2.0
    r_max = width / 2.0 - 2.0

    for y in range(height):
        for x in range(width):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            idx = (y * width + x) * 4

            # Background circle (blue #2563EB -> RGB 37, 99, 235)
            if dist <= r_max:
                # Anti-aliasing edge
                alpha = 255
                if dist > r_max - 1.0:
                    alpha = int(255 * (r_max - dist))

                # Radar rings & antenna dot
                is_ring1 = abs(dist - 14) < 1.5
                is_ring2 = abs(dist - 9) < 1.5
                is_center = dist < 4.5
                is_beam = (dx >= 0 and dy <= 0 and abs(dx - (-dy)) < 2.0)

                if is_center or is_ring1 or is_ring2 or is_beam:
                    # White icon elements
                    pixels[idx] = 255      # R
                    pixels[idx + 1] = 255  # G
                    pixels[idx + 2] = 255  # B
                    pixels[idx + 3] = alpha
                else:
                    # Blue base
                    pixels[idx] = 37       # R
                    pixels[idx + 1] = 99   # G
                    pixels[idx + 2] = 235  # B
                    pixels[idx + 3] = alpha
            else:
                # Transparent outside
                pixels[idx] = 0
                pixels[idx + 1] = 0
                pixels[idx + 2] = 0
                pixels[idx + 3] = 0

    # Encode as minimal PNG
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_scanlines = bytearray()
    for y in range(height):
        raw_scanlines.append(0) # filter type none
        raw_scanlines.extend(pixels[y * width * 4:(y + 1) * width * 4])

    idat = zlib.compress(bytes(raw_scanlines), 9)
    png_bytes = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    return png_bytes

def create_ico(ico_path):
    png_data = create_png_radar(48, 48)
    # Write Windows ICO wrapping the PNG
    header = struct.pack("<HHH", 0, 1, 1) # reserved, type=1 (ico), 1 image
    # Directory entry
    # width, height, colors, reserved, planes, bpp, bytes_in_res, offset
    dir_entry = struct.pack("<BBBBHHII", 48, 48, 0, 0, 1, 32, len(png_data), 6 + 16)
    with open(ico_path, "wb") as f:
        f.write(header)
        f.write(dir_entry)
        f.write(png_data)
    print(f"Created icon at: {ico_path}")

def create_shortcut(desktop_path, project_dir):
    ico_path = os.path.join(project_dir, "app_icon.ico")
    create_ico(ico_path)

    bat_path = os.path.join(project_dir, "start_windows.bat")
    lnk_path = os.path.join(desktop_path, "BLE Tracker Search.lnk")

    # Use PowerShell via Windows script host to create shortcut
    import subprocess
    ps_cmd = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{lnk_path}')
$s.TargetPath = '{bat_path}'
$s.WorkingDirectory = '{project_dir}'
$s.Description = 'Windows BLE Tracker Search - Security Pilot'
$s.IconLocation = '{ico_path},0'
$s.Save()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)
    print(f"Created shortcut at: {lnk_path}")

if __name__ == "__main__":
    proj_dir = os.path.abspath(os.path.dirname(__file__))
    desktop = os.path.expanduser("~/Desktop")
    create_shortcut(desktop, proj_dir)

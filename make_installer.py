"""
Windows Packager Script - Generates a small portable install script
"""
import os, zipfile, io, base64

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk('src'):
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(root, f)
                z.write(p)
    for root, dirs, files in os.walk('rules'):
        for f in files:
            if f.endswith('.json'):
                p = os.path.join(root, f)
                z.write(p)
    for root, dirs, files in os.walk('dist'):
        for f in files:
            p = os.path.join(root, f)
            z.write(p)
    z.write('requirements.txt')
    z.write('main.py')
    z.write('start_windows.bat')

zip_bytes = buf.getvalue()
print('Payload zip size:', len(zip_bytes))
with open('/tmp/payload.zip', 'wb') as f:
    f.write(zip_bytes)

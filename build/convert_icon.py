#!/usr/bin/env python3
"""
Convert source icon (icon-source.png) to all platform-specific formats.

Usage:
    python build/convert_icon.py
"""

from PIL import Image
import os
import subprocess
import platform


def convert_to_icns(source_png, output_icns):
    """Convert PNG to macOS ICNS format.
    
    Args:
        source_png: Source PNG file (should be 1024x1024)
        output_icns: Output ICNS file
    """
    if platform.system() != 'Darwin':
        print(f'⚠️  ICNS conversion works best on macOS. Attempting PNG fallback...')
        # On non-macOS, just save as PNG with .icns extension (won't work perfectly)
        img = Image.open(source_png)
        img.save(output_icns.replace('.icns', '.png'))
        return
    
    # Use macOS sips tool (preferred method)
    try:
        subprocess.run([
            'sips', '-s', 'format', 'icns',
            source_png, '--out', output_icns
        ], check=True, capture_output=True)
        print(f'✅ Created {output_icns}')
    except subprocess.CalledProcessError as e:
        print(f'❌ Failed with sips, trying iconutil...')
        # Fallback: create iconset and use iconutil
        try:
            iconset_dir = output_icns.replace('.icns', '.iconset')
            os.makedirs(iconset_dir, exist_ok=True)
            
            img = Image.open(source_png)
            
            # Generate all required sizes for ICNS
            sizes = [
                (16, 'icon_16x16.png'),
                (32, 'icon_16x16@2x.png'),
                (32, 'icon_32x32.png'),
                (64, 'icon_32x32@2x.png'),
                (128, 'icon_128x128.png'),
                (256, 'icon_128x128@2x.png'),
                (256, 'icon_256x256.png'),
                (512, 'icon_256x256@2x.png'),
                (512, 'icon_512x512.png'),
                (1024, 'icon_512x512@2x.png'),
            ]
            
            for size, name in sizes:
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                resized.save(os.path.join(iconset_dir, name))
            
            # Convert iconset to icns
            subprocess.run([
                'iconutil', '-c', 'icns', iconset_dir, '-o', output_icns
            ], check=True)
            
            # Clean up iconset
            import shutil
            shutil.rmtree(iconset_dir)
            
            print(f'✅ Created {output_icns}')
        except Exception as e2:
            print(f'❌ Failed to create ICNS: {e2}')


def convert_to_ico(source_png, output_ico):
    """Convert PNG to Windows ICO format.
    
    Args:
        source_png: Source PNG file
        output_ico: Output ICO file
    """
    try:
        img = Image.open(source_png)
        
        # Create multiple sizes for ICO
        sizes = [(256, 256), (128, 128), (96, 96), (64, 64), (48, 48), (32, 32), (16, 16)]
        
        # Save ICO with all sizes
        img.save(output_ico, format='ICO', sizes=sizes)
        print(f'✅ Created {output_ico}')
    except Exception as e:
        print(f'❌ Failed to create ICO: {e}')


def convert_to_png_formats(source_png, output_dir):
    """Convert to Linux PNG formats (512x512).
    
    Args:
        source_png: Source PNG file
        output_dir: Output directory (e.g., build/linux)
    """
    try:
        img = Image.open(source_png)
        
        # Create 512x512 for Linux
        img_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
        img_512.save(os.path.join(output_dir, 'qlayout.png'))
        print(f'✅ Created {os.path.join(output_dir, "qlayout.png")}')
    except Exception as e:
        print(f'❌ Failed to create PNG: {e}')


if __name__ == '__main__':
    source = 'build/icon-source.png'
    
    if not os.path.exists(source):
        print(f'❌ Source icon not found: {source}')
        print(f'   Please place your 1024x1024 PNG icon at: {source}')
        exit(1)
    
    # Check source dimensions
    img = Image.open(source)
    if img.size != (1024, 1024):
        print(f'⚠️  Warning: Icon is {img.size[0]}x{img.size[1]}, expected 1024x1024')
        print(f'   Continuing anyway...')
    
    print(f'🎨 Converting {source} to platform-specific formats...\n')
    
    # macOS ICNS
    print('Converting to macOS ICNS...')
    convert_to_icns(source, 'build/macos/qlayout.icns')
    
    # Windows ICO
    print('\nConverting to Windows ICO...')
    convert_to_ico(source, 'build/windows/qlayout.ico')
    
    # Linux PNG
    print('\nConverting to Linux PNG...')
    convert_to_png_formats(source, 'build/linux')
    
    print('\n✅ Icon conversion complete!')
    print('\nGenerated files:')
    print('  - build/macos/qlayout.icns')
    print('  - build/windows/qlayout.ico')
    print('  - build/linux/qlayout.png')

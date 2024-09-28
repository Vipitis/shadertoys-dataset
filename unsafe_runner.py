# this is the runner script


from wgpu_shadertoy import Shadertoy
from wgpu.utils.device import get_default_device
import sys

def init():
    # this is the slow part
    get_default_device()


def run_shader(shader_code):
    shader = Shadertoy(shader_code, shader_type="glsl", offscreen=True)
    try:
        snap1 = shader.snapshot(12.34)
        snap2 = shader.snapshot(56.78)
        return "ok"
    except Exception as e:
        return f"error: {e}"

if __name__ == "__main__":
    init()
    while True:
        shader_code = sys.stdin.read()
        if shader_code.strip() == "exit":
            break
        result = run_shader(shader_code)
        sys.stdout.write(result + "\\n")
        sys.stdout.flush()
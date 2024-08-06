import multiprocessing

from wgpu_shadertoy import Shadertoy
from tqdm.auto import tqdm

new_code = """
void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    // Normalized pixel coordinates (from 0 to 1)
    vec2 uv = fragCoord/iResolution.xy;

    // Time varying pixel color
    vec3 col = 0.5 + 0.5*cos(iTime+uv.xyx+vec3(0,2,4));

    // Output to screen
    fragColor = vec4(col,1.0);
}
"""


error_code = """
void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    // Normalized pixel coordinates (from 0 to 1)
    vec2 uv = fragCoord/iResolution.xy;

    // Time varying pixel color
    vec3 col = 0.5 + 0.5*cos(iTime+uv.xyx+vec3(0,2,4));

    // Output to screen
    fragColor = vec4(coll,1.0);
}
"""

# this panics because it loses device
minimal_code = """
void mainImage( out vec4 fragColor, in vec2 fragCoord ) {

    vec3 col = vec3(0.0);
    float incr = 0.1;
    for (float i = 0.5; i < 3.0; i += max(0.0, iTime)) {
        col += vec3(0.2);
        // continue;
    }
    fragColor = vec4(col, 1.0);
}
"""


def minimal_run(shader_code, return_dict):
    try:
        shader = Shadertoy(shader_code, shader_type="glsl", offscreen=True)
        # shader.show()
        shader.snapshot(0.0)
        return_dict['result'] = "ok"
    except Exception as e:
        return_dict['result'] = f"error: {e}"

def run_shader_code(shader_code, timeout):
    manager = multiprocessing.Manager()
    return_dict = manager.dict()
    process = multiprocessing.Process(target=minimal_run, args=(shader_code, return_dict))
    process.start()
    process.join(timeout)

    if process.is_alive():
        process.terminate()
        process.join()
        return "timeout"
    else:
        return return_dict.get('result', 'error: unknown (likely panic)')

if __name__ == "__main__":
    shader_codes = [new_code, error_code, minimal_code]
    TIMEOUT = 10

    results = []
    for shader_code in tqdm(shader_codes * 10):
        result = run_shader_code(shader_code, TIMEOUT)
        results.append(result)
        print(result)
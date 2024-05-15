import json
import jsonlines
import os
import datetime
import tree_sitter  # do we want this here -> annotate function byte-indecies?
import argparse
import tqdm
import evaluate

from licensedcode.detection import detect_licenses


from wgpu_shadertoy import Shadertoy

shadermatch = evaluate.load("Vipitis/shadermatch")

argument_parser = argparse.ArgumentParser()
argument_parser.add_argument("--input", type=str, required=False, default="./data/raw/")
argument_parser.add_argument(
    "--output", type=str, required=False, default="./data/annotated/"
)


def annotate(shader_data: dict, access: str="api") -> dict:
    """
    Functions calls a bunch of smaller functions to annotate and flatten a instance of a shader_data json respose
    Returns a flattened dict that is a dataset insanace
    """
    if "Shader" in shader_data:
        shader_data = shader_data["Shader"]
    out_dict = flatten_shader_data(shader_data)
    out_dict["license"] = classify_license(out_dict["image_code"])
    out_dict["thumbnail"] = (
        f"https://www.shadertoy.com/media/shaders/{shader_data['info']['id']}.jpg"
    )
    out_dict["time_retrieved"] = datetime.datetime.now().isoformat()
    out_dict["access"] = access # api, unlisted, public/scraped? not sure yet.
    out_dict["wgpu-test"] = try_shader(shader_data={"Shader": shader_data},image_code=out_dict["image_code"]) # to avoid calling API once again.

    return out_dict

def flatten_shader_data(shader_data: dict) -> dict:
    """
    Falttens all renderpasses into a single depth dict, adds None where not present
    """
    if "Shader" in shader_data:
        shader_data = shader_data["Shader"]
    out_dict = {}

    out_dict["id"] = shader_data["info"]["id"]
    out_dict["name"] = shader_data["info"]["name"]
    out_dict["author"] = shader_data["info"]["username"]
    out_dict["description"] = shader_data["info"]["description"]
    out_dict["tags"] = shader_data["info"]["tags"]
    out_dict["time_retrieved"] = shader_data["time_retrieved"]

    pass_names = [
        "Image",
        "Common",
        "Sound",
        "Buffer A",
        "Buffer B",
        "Buffer C",
        "Buffer D",
        "Cube A",
    ]
    for rp in shader_data["renderpass"]:
        # remove the pass name from the list
        try:
            pass_names.remove(rp["name"])  # TODO: test for value error here? ('', 'Buffer @', 'none', 'Buf C', 'Text Lib', 'Buf A', 'Buf B', 'Buf D')
        except ValueError:
            print(f"Pass name not standard: {rp['name']=}, skipping...")
            continue
        out_dict[f"{rp['name'].replace(' ', '_').lower()}_code"] = rp.get("code", "")
        out_dict[f"{rp['name'].replace(' ', '_').lower()}_inputs"] = rp.get(
            "inputs", []
        )
    for name in pass_names:
        out_dict[f"{name.replace(' ', '_').lower()}_code"] = ""
        out_dict[f"{name.replace(' ', '_').lower()}_inputs"] = []

    del out_dict["common_inputs"]  # this never exists

    return out_dict


def classify_license(code: str) -> str:
    """
    Returns the spdx license identifier, if the shadercode specifies it at the top. Defaults to "cc-by-nc-sa-3.0" by default.
    """
    
    detections = [x.matches[0] for x in detect_licenses(query_string=code) if x.matches[0].lines()[0] < 5] # TODO: find a better solution than hardcoding 5
    if len(detections) == 0:
        return "cc-by-nc-sa-3.0"
    return detections[0].to_dict().get("license_expression", None)

def try_shader(shader_data: dict, image_code: str) -> str:
    """
    Tests a shader by running it in wgpu-shadertoy. Returns one of the following:
    "ok" - shader ran without error
    "incomplete" - not yet fully supported in wgpu-shadertoy
    "error" - wgpu-shadertoy threw and error (is likely still valid on the website)
    "panic" - worst case scenario. a rust panic in wgpu. This can cause the python process to terminate without recovery.
    """

    # code snippet from elsewhere, ref: https://huggingface.co/spaces/Vipitis/shadermatch/blob/main/shadermatch.py#L141-L157
    try:
        shadermatch.validate_shadertoy(image_code) #only checks the main image pass, could still crash if common or other passes have issues...
    except Exception as e:
        if isinstance(e, ValueError):
            print(f"ValueError: {e} for shader {shader_data['Shader']['info']['id']=}, counts as error")
            return "error"
        if "panicked" in e.message or "timedout" in e.message:
            return "panic"
        else:
            return "error"
    try:
        shader = Shadertoy.from_json(shader_data, offscreen=True)
        # shader.show() not required I think...
    except Exception as e:
        return "error"
    if not shader.complete:
        return "incomplete"
    return "ok"



if __name__ == "__main__":
    args = argument_parser.parse_args()
    input_dir = args.input
    output_dir = args.output

    for file in os.listdir(input_dir):
        if file.endswith(".jsonl"):
            print(f"Annotating {file}")
            with jsonlines.open(os.path.join(input_dir, file), "r") as reader:
                shaders = list(reader)
            annotated_shaders = []
            for shader in tqdm.tqdm(shaders):
                annotated_shaders.append(annotate(shader))
            output_path = os.path.join(output_dir, file)
            with jsonlines.open(output_path, mode="w") as writer:
                for shader in annotated_shaders:
                    writer.write(shader)
            print(f"Annotated {file} to {output_path}")


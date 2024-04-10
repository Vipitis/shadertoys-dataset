import json
import jsonlines
import os
import datetime
import tree_sitter  # do we want this here
import argparse

from wgpu_shadertoy import Shadertoy

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
    out_dict["license"] = detect_license(shader_data)
    out_dict["thumbnail"] = (
        f"https://www.shadertoy.com/media/shaders/{shader_data['info']['id']}.jpg"
    )
    out_dict["time_retrieved"] = datetime.datetime.now().isoformat()
    out_dict["access"] = access # api, unlisted, public/scraped? not sure yet.

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
        pass_names.remove(rp["name"])  # TODO: test for value error here? ('', 'Buffer @', 'none', 'Buf C', 'Text Lib', 'Buf A', 'Buf B', 'Buf D')
        out_dict[f"{rp['name'].replace(' ', '_').lower()}_code"] = rp.get("code", "")
        out_dict[f"{rp['name'].replace(' ', '_').lower()}_inputs"] = rp.get(
            "inputs", []
        )
    for name in pass_names:
        out_dict[f"{name.replace(' ', '_').lower()}_code"] = ""
        out_dict[f"{name.replace(' ', '_').lower()}_inputs"] = []

    del out_dict["common_inputs"]  # this never exists

    return out_dict


def detect_license(shader_data) -> str:
    """
    Function to detect the license of a shader using ScanCode.
    """
    return "default"


if __name__ == "__main__":
    args = argument_parser.parse_args()
    input_dir = args.input
    output_dir = args.output

    for file in os.listdir(input_dir):
        if file.endswith(".jsonl"):
            with jsonlines.open(os.path.join(input_dir, file), "r") as reader:
                shaders = list(reader)
            annotated_shaders = [annotate(shader_data) for shader_data in shaders]
            output_path = os.path.join(output_dir, file)
            with jsonlines.open(output_path, mode="w") as writer:
                for shader in annotated_shaders:
                    writer.write(shader)
            print(f"Annotated {file} to {output_path}")


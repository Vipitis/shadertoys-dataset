import json
import jsonlines
import os
import datetime
import tree_sitter  # do we want this here
import argparse

from wgpu_shadertoy import Shadertoy

argument_parser = argparse.ArgumentParser()
argument_parser.add_argument("--input", type=str, required=True, default="./data/raw/")
argument_parser.add_argument(
    "--output", type=str, required=True, default="./data/annotated/"
)


def annotate(shader_data) -> dict:
    """
    Functions calls a bunch of smaller functions to annotate and flatten a instance of a shader_data json respose
    Returns a flattened dict that is a dataset insanace
    """
    out_dict = flatten_shader_data(shader_data)
    out_dict["license"] = detect_license(shader_data)
    out_dict[
        "thumbnail"
    ] = f"https://www.shadertoy.com/media/shaders/{shader_data["info"]["id"]}.jpg"
    out_dict["time_retrieved"] = datetime.datetime.now().isoformat()


def flatten_shader_data(shader_data) -> dict:
    """
    Falttens all renderpasses into a single depth dict, adds None where not present
    """
    out_dict = {}
    out_dict["id"] = shader_data["info"]["id"]
    out_dict["name"] = shader_data["info"]["name"]
    out_dict["author"] = shader_data["info"]["username"]


def detect_license(shader_data) -> str:
    """
    Function to detect the license of a shader using ScanCode.
    """
    return "default"


if __name__ == "__main__":
    args = argument_parser.parse_args()

import requests
import json
import jsonlines
import gzip
import tqdm

import argparse
import os
import datetime

SHADERTOY_KEY = os.getenv("SHADERTOY_KEY")
HEADERS = {
    "user-agent": "python script to download shadertoys dataset for: https://github.com/Vipitis/shadertoys-dataset"
}

argument_parser = argparse.ArgumentParser()

argument_parser.add_argument(
    "--mode",
    type=str,
    default="update",
    help="Mode to download the dataset: full, append or update",
)
argument_parser.add_argument(
    "--output_dir",
    type=str,
    default="./data/raw/",
    help="Output directory for the dataset",
)
argument_parser.add_argument(
    "--ids",
    type=str,
    default=None,
    help="List of shaderIDs or URLs to download/update (can be a .txt file) or space separated list of ids",
)
argument_parser.add_argument(
    "--num_shaders",
    type=int,
    default=None,
    help="Number of shaders to download, overwritten if ids is provided",
)


def get_all_shaders():
    url = "https://www.shadertoy.com/api/v1/shaders"
    response = requests.get(
        url, params={"key": SHADERTOY_KEY, "sort": "newest"}, headers=HEADERS
    )
    if response.status_code != 200:
        raise requests.exceptions.HTTPError(
            f"Failed to load shaders with status code {response.status_code}"
        )
    return response.json()["Results"]


def get_shader(shader_id) -> dict:
    url = f"https://www.shadertoy.com/api/v1/shaders/{shader_id}"
    response = requests.get(url, params={"key": SHADERTOY_KEY}, headers=HEADERS)
    if response.status_code != 200:
        raise requests.exceptions.HTTPError(
            f"Failed to load shader {shader_id} with status code {response.status_code}"
        )
    shader_data = response.json()
    if "Error" in shader_data:
        raise ValueError(f"Failed to load shader {shader_id}: {shader_data['Error']}") #TODO: consider scraping here: https://github.com/pygfx/shadertoy/pull/27
    
    shader_data["Shader"]["time_retrieved"] = datetime.datetime.now().isoformat()
    return shader_data


def append_shaders(output_path, shaders: list[dict]) -> None:
    """
    Appends shaders to a given jsonlines file.
    """
    with jsonlines.open(output_path, mode="a") as writer:
        for shader in shaders:
            writer.write(shader)


def update_shaders(output_path, shaders: list[dict]) -> None:
    # TODO: test and fix this!
    """
    Updates shaders in a given jsonlines file.
    """
    with jsonlines.open(output_path, mode="r") as reader:
        existing_shaders = list(reader)
    existing_ids = set([shader["info"]["id"] for shader in existing_shaders])
    new_shaders = [
        shader for shader in shaders if shader["info"]["id"] not in existing_ids
    ]
    append_shaders(output_path, new_shaders)


def read_ids(ids_path):
    with open(ids_path, "r", encoding="utf-8") as f:
        return f.read().splitlines()
    
def extract_id(id_or_url):
    """
    Helper function to extract jus the id, even if urls are given.
    """
    if "/" in id_or_url:
        shader_id = id_or_url.rstrip("/").split("/")[-1]
    else:
        shader_id = id_or_url
    return shader_id

if __name__ == "__main__":
    args = argument_parser.parse_args()
    if args.mode == "full":
        shader_ids = get_all_shaders()
    if args.ids is not None:
        if args.ids.endswith(".txt"):
            shader_ids = read_ids(args.ids)
        else:
            shader_ids = args.ids.split(" ")
        # overwrite num_shaders here as well?
    shader_ids = [extract_id(id) for id in shader_ids]

    if args.num_shaders is not None:
        shader_ids = shader_ids[:args.num_shaders]
    num_ids = len(shader_ids)
    if num_ids > 1000:
        raise NotImplementedError("Chunking not yet implemented")
    first_id = shader_ids[0]
    last_id = shader_ids[-1]
    output_path = os.path.join(args.output_dir, f"{first_id}_{last_id}.jsonl")
    print(f"Total number of shaders ids: {num_ids}")

    for shader_id in tqdm.tqdm(shader_ids):
        shader = get_shader(shader_id)
        append_shaders(output_path, [shader])
    print(f"Downloaded {num_ids} shaders to {output_path}")

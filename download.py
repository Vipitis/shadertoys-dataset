import requests
import json
import jsonlines
import tqdm

import shutil
import argparse
import os
import datetime
import tempfile
import zipfile

SHADERTOY_KEY = os.getenv("SHADERTOY_KEY")
HEADERS = {
    "user-agent": "python script to download shadertoys dataset for: https://github.com/Vipitis/shadertoys-dataset"
}

argument_parser = argparse.ArgumentParser()

argument_parser.add_argument(
    "--mode",
    type=str,
    default="update",
    help="Mode to download the dataset: shaders20k, full, append or update",
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


def scrape_to_api(json_data: dict) -> dict:
    """
    transform the dict to be exactly like the API return would provide it
    """
    shader_data = {
        "Shader": {
            "info": json_data["info"],
            "ver": json_data["ver"],
            "renderpass": json_data["renderpass"],
        }
    }
    del shader_data["Shader"]["info"]["usePreview"]
    for rp in shader_data["Shader"]["renderpass"]:
        for inp in rp["inputs"]:
            inp["src"] = inp.pop("filepath")
            inp["ctype"] = inp.pop("type")

    return shader_data


def get_shaders20k(data_dir="./data/raw/"):
    zip_path = os.path.join(data_dir, "shaders20k", "all_codes.zip")
    # ./data/ids/shaders20k.txt
    ids_dest = os.path.abspath("./data/ids/shaders20k.txt")
    if not os.path.exists(zip_path):
        raise NotImplementedError(
            "use the original script for now: https://github.com/mbaradad/shaders21k/blob/main/scripts/download/download_shader_codes.sh"
        )

    # ids in shader_codes/shaders_info/shadertoy_urls -> save to data/ids/shaders20k.txt
    # shader files in shader_codes/shadertoy/*/ID.frag -> save to data/raw/shaders20k_*.jsonl
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
        if not os.path.exists(ids_dest):
            shutil.move(
                os.path.join(
                    temp_dir, "shader_codes", "shaders_info", "shadertoy_urls"
                ),
                ids_dest,
            )
        for root, dir, files in os.walk(
            os.path.join(temp_dir, "shader_codes", "shadertoy")
        ):
            print(root, dir)
            shaders = []
            subdir = root.split("\\")[-1]
            print(subdir)
            # break
            output_path = os.path.join(data_dir, f"shaders20k_{subdir}.jsonl")
            for file in files:
                # print(file)
                # break
                with open(os.path.join(root, file), "r") as f:
                    shader_data = json.loads(f.read())
                shader_data = scrape_to_api(shader_data)
                shader_data["Shader"]["time_retrieved"] = datetime.datetime(
                    year=2021, month=10, day=1
                ).isoformat()  # Ocotber 2021 according to repo
                shaders.append(shader_data)
            append_shaders(output_path, shaders)


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
        raise ValueError(
            f"Failed to load shader {shader_id}: {shader_data['Error']}"
        )  # TODO: consider scraping here: https://github.com/pygfx/shadertoy/pull/27

    shader_data["Shader"]["time_retrieved"] = datetime.datetime.now().isoformat()
    return shader_data


def append_shaders(output_path, shaders: list[dict]) -> None:
    """
    Appends shaders to a given jsonlines file.
    """
    # TODO: overwrite if already exists!
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
    print(args)
    if args.mode == "shaders20k":
        get_shaders20k()
        exit()

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
        shader_ids = shader_ids[: args.num_shaders]
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

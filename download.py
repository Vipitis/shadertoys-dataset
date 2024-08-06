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
    privacy_keys = {0: "Private", 1: "Public", 2: "Unlisted", 3: "Public API", 4: "Anonymous"}
    
    shader_data = {
        "Shader": {
            "info": json_data["info"],
            "ver": json_data["ver"],
            "renderpass": json_data["renderpass"],
        }
    }
    # del shader_data["Shader"]["info"]["usePreview"] # indicates if a shader is "heavy" and should not be rendered in preview. Maybe useful for filtering?
    for rp in shader_data["Shader"]["renderpass"]:
        for inp in rp["inputs"]:
            inp["src"] = inp.pop("filepath")
            inp["ctype"] = inp.pop("type")

    # TODO: that seems be be incorrect, download gives these. scrape and API gives numbers -.-
    shader_data["Shader"]["info"]["published"] = privacy_keys.get(shader_data["Shader"]["info"]["published"], "Unknown")

    return shader_data


def get_shaders20k(data_dir="./data/raw/"):
    zip_path = os.path.join(data_dir, "shaders20k", "all_codes.zip")
    # ./data/ids/shaders20k.txt
    ids_dest = os.path.abspath("./data/ids/shaders20k.txt")
    date_20k = datetime.datetime(year=2021, month=10, day=1).isoformat()  # Ocotber 2021 according to repo

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
        for root, dir, files in tqdm.tqdm(os.walk(
            os.path.join(temp_dir, "shader_codes", "shadertoy")
        )):
            if not files:
                # skip this the empty dir?
                continue
            # break
            # output_path = os.path.join(data_dir, f"shaders20k_{subdir}.jsonl")
            for file in tqdm.tqdm(files):
                # break
                with open(os.path.join(root, file), "r") as f:
                    shader_data = json.loads(f.read())
                shader_data = scrape_to_api(shader_data)
                shader_date = datetime.datetime.fromtimestamp(
                    float(shader_data["Shader"]["info"]["date"])
                ).strftime("%Y-%m")
                output_path = os.path.join(data_dir, f"20k_{shader_date}.jsonl")
                shader_data["Shader"]["time_retrieved"] = date_20k
                append_shaders(output_path, [shader_data])
                # shaders.append(shader_data)


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

    print(f"Total number of shaders ids: {num_ids}")

    for shader_id in tqdm.tqdm(shader_ids):
        shader = get_shader(shader_id)
        # from unix timestamp to year and month
        shader_date = datetime.datetime.fromtimestamp(
            float(shader["Shader"]["info"]["date"])
        ).strftime("%Y-%m")
        output_path = os.path.join(args.output_dir, f"{shader_date}.jsonl")
        append_shaders(output_path, [shader])
    print(f"Downloaded {num_ids} shaders to {output_path}")

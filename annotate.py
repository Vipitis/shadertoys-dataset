import json
from argon2 import Type
import jsonlines
import os
import datetime
import argparse
import tqdm
import evaluate
import tree_sitter_glsl as tsglsl
from tree_sitter import Language, Parser
from typing import List, Tuple
from wgpu_shadertoy import Shadertoy
from licensedcode.detection import detect_licenses

from wgpu_shadertoy.api import shader_args_from_json

GLSL_LANGUAGE = Language(tsglsl.language())
PARSER = Parser(GLSL_LANGUAGE)

shadermatch = evaluate.load("Vipitis/shadermatch")

argument_parser = argparse.ArgumentParser()
argument_parser.add_argument("--input", type=str, required=False, default="./data/raw/", help="the path of raw shadertoy api returns .jsonl")
argument_parser.add_argument("--output", type=str, required=False, default="./data/annotated/", help="the path of where to store annotated shaders as .jsonl")
argument_parser.add_argument("--mode", type=str, default="update", help="mode `update` will load shaders already in the output folder and overwrite specified columns; mode `redo` will overwrite the whole file")
argument_parser.add_argument("--columns", type=str, required=True, help="comma separated list of columns to annotate: all, license, functions, test; if empty will simply faltten the nested structure") 
# TODO: is --mode "update" --columns "all" is the same as --mode "redo"?


def annotate_shader(shader_data: dict, columns: list, access: str = "api") -> dict:
    """
    Functions calls a bunch of smaller functions to annotate and flatten a instance of a shader_data json respose
    Returns a flattened dict that is a dataset insanace
    """
    if "Shader" in shader_data:
        shader_data = shader_data["Shader"]
    out_dict = flatten_shader_data(shader_data)
    out_dict["thumbnail"] = (
        f"https://www.shadertoy.com/media/shaders/{shader_data['info']['id']}.jpg"
    )
    out_dict["access"] = access  # api, shaders20k, ?

    # overwrite to update?
    out_dict = update_shader(out_dict, columns=columns)

    return out_dict

def update_shader(flattened_shader: dict, columns: list) -> dict:
    updated_shader = flattened_shader.copy() # do we need that?
    
    cols_to_update = columns.copy() #seems redundant
    if "all" in columns:
        cols_to_update = list(COLUMN_MAP.keys())
    for col in cols_to_update:
        col_func = COLUMN_MAP[col]
        updated_shader.update({col: col_func(flattened_shader)})
    # TODO: set None for cols not mentioned?

    return updated_shader


def flatten_shader_data(shader_data: dict) -> dict:
    """
    Falttens all renderpasses into a single depth dict.
    """
    if "Shader" in shader_data:
        shader_data = shader_data["Shader"]
    out_dict = {}

    # we lift some information out of the "info" dict that are useful
    out_dict["id"] = shader_data["info"]["id"]
    out_dict["name"] = shader_data["info"]["name"]
    out_dict["author"] = shader_data["info"]["username"]
    out_dict["description"] = shader_data["info"]["description"]
    out_dict["tags"] = shader_data["info"]["tags"]
    out_dict["likes"] = shader_data["info"]["likes"]
    out_dict["viewed"] = shader_data["info"]["viewed"]
    out_dict["published"] = shader_data["info"]["published"] # download uses {0: "Private", 1: "Public", 2: "Unlisted", 3: "Public API", 4: "Anonymous"}
    out_dict["date"] = shader_data["info"]["date"] # maybe format into a readable format or at least int?
    # this one is added by us wiht the download.py script
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
        # if there is just one pass, it has to be the image Pass.
        if len(shader_data["renderpass"]) == 1:
            rp["name"] = "Image"

        # remove the pass name from the list
        try:
            pass_names.remove(rp["name"])  
        except ValueError:
            # TODO: find a solution for some of these unknown names: ('', 'Buffer @', 'none', 'Buf C', 'Text Lib', 'Buf A', 'Buf B', 'Buf D')
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


def check_license(code_or_shader) -> str:
    """
    Returns the license mentioned if the first node is a comment.
    if none is found, or no comment, returns "CC-BY-NC-SA-3.0" as the base case.
    """
    if isinstance(code_or_shader, dict):
        code = code_or_shader["image_code"]
    elif isinstance(code_or_shader, str):
        code = code_or_shader
    else:
        raise TypeError(f" function doesn't support {type(code_or_shader)}")


    tree = PARSER.parse(bytes(code, encoding="utf-8"))
    comment_bytes = b""
    cursor = tree.walk()
    cursor.goto_first_child()
    # is a while node really a good idea?
    while cursor.node.type == "comment":
        comment_bytes += cursor.node.text
        cursor.goto_next_sibling()
    if comment_bytes:
        detections = [x.matches[0] for x in detect_licenses(query_string=comment_bytes.decode(encoding="utf-8"))]
        if len(detections) >= 1:
            return detections[0].to_dict().get("license_expression", None)
    
    # base case is capitalized for downstream analysis
    return "CC-BY-NC-SA-3.0"


def parse_functions(code_or_shader) -> List[Tuple[int,int,int,int,int]]:
    """
    parses the code using tree-parser-glsl
    returns the **byte-indecies** for before_comment, start header, end header, end docstring, end_function.
    returns a list 5-tupel. If before_comment or docstring aren't found, the indiecies will coinside with the next one.
    """
    # TODO: dry and maybe have it code_or_tree?
    if isinstance(code_or_shader, dict):
        code = code_or_shader["image_code"]
    elif isinstance(code_or_shader, str):
        code = code_or_shader
    else:
        raise TypeError(f" function doesn't support {type(code_or_shader)}")

    tree = PARSER.parse(bytes(code, encoding="utf-8"))
    root_node = tree.root_node
    funcs = []
    
    # lazy init
    start_comment = start_header = end_header = end_docstring = end_function = None
    comment_line = -2 #init with a different number?
    for child in root_node.children:
        if (child.type == "comment"):
            if ((comment_line + 1) != child.start_point[0]): # and child.start_point[1] == 0 # and not child.start_point[1] # so we only get whole line comments, nothing inline. but tabs or indentation might be an issue?
                start_comment = child.start_byte
            comment_line = child.end_point[0]
        elif child.type == "function_definition":
            start_header = child.start_byte
            if comment_line == -2 and not start_comment: # so we can also get multi line comments at the start (but inline comments?)
                start_comment = start_header
            end_function = child.end_byte
            end_header = child.children[-1].children[0].end_byte
            # inside the function body, past the "{"
            for sub_child in child.children[-1].children[1:]:
                if sub_child.type == "comment":
                    end_docstring = sub_child.end_byte
                else:
                    if not end_docstring:
                        end_docstring = end_header
                    break #which part does this break out of? early stopping somehow...

            funcs.append(tuple([start_comment, start_header, end_header, end_docstring, end_function]))
            start_comment = start_header = end_header = end_docstring = end_function = None
            comment_line = -2 # so out empty check can work again
    return funcs


def try_shader(shader_data: dict) -> str:
    """
    Tests a shader by running it in wgpu-shadertoy. Returns one of the following disjunct classes:
    "ok" - shader ran without error
    "incomplete" - not yet fully supported in wgpu-shadertoy
    "error" - wgpu-shadertoy threw and error (is likely still valid on the website)
    "panic" - worst case scenario. a rust panic in wgpu. This can cause the python process to terminate without recovery.
    "timeout" - if after 5 seconds we don't get to error or okay.
    """
    # TODO: refactor out the use of the evaluate module here. Just subprocess to try/except - no more naga.
    # should there be an "untested" results if there is an unrelated error with like cache files for example?
    if "Shader" not in shader_data:
        shader_data["Shader"] = shader_data
    
    image_code = shader_data["image_code"]
    # code snippet from elsewhere, ref: https://huggingface.co/spaces/Vipitis/shadermatch/blob/main/shadermatch.py#L141-L157
    try:
        shadermatch.validate_shadertoy(
            image_code
        )  # only checks the main image pass, could still crash if common or other passes have issues...
    except Exception as e:
        print(e)
        if isinstance(e, ValueError):
            print(
                f"ValueError: {e} for shader {shader_data['Shader']['info']['id']=}, counts as error"
            )
            return "error"
        if "panicked" in e.message:
            return "panic"
        elif "timedout" in e.message:
            return "timeout"
        else:
            return "error"
    try:
        #TODO: this doesn't work for flattened variant right now... need to map my custom cols to the original format again?
        # shader_args = shader_args_from_json(shader_data["Shader"])
        # if not shader_args["complete"]:
        #     return "incomplete"
        shader = Shadertoy(shader_code=image_code, offscreen=True)
        # shader.show() not required I think...
    except Exception as e:
        print(e.message)
        return "error" # could be API error? maybe put untested
    return "ok"

# gloablly map all columns to the function that calculate them. might need to REGISTER more?
COLUMN_MAP = {"license": check_license, "functions": parse_functions, "test": try_shader}

if __name__ == "__main__":
    args = argument_parser.parse_args()
    print(f"{args=}")
    input_dir = args.input
    output_dir = args.output
    columns = [col.strip() for col in args.columns.split(",")] #if col in list(COLUMN_MAP.values()) + ["all"]]
    print(f"{columns=}")


    if args.mode == "redo":
        print(f"annotating all .jsonlines files in {input_dir}")
        for file in tqdm.tqdm(os.listdir(input_dir)):
            if not file.endswith(".jsonl"):
                tqdm.tqdm.write(f"Skipping file {file}")
            source = "api" #default?
            if file.startswith("20k"): #should we do api_ prefix for the others?
                source = "shaders20k"
            tqdm.tqdm.write(f"Annotating {file}")
            with jsonlines.open(os.path.join(input_dir, file), "r") as reader:
                shaders = list(reader)
            annotated_shaders = []
            for shader in tqdm.tqdm(shaders):
                annotated_shaders.append(annotate_shader(shader, columns=columns, access=source))
            
            output_path = os.path.join(output_dir, file)
            with jsonlines.open(output_path, mode="w") as writer:
                for shader in annotated_shaders:
                    writer.write(shader)
            tqdm.tqdm.write(f"Annotated {file} to {output_path}")

    elif args.mode == "update":
        print(f"updating all .jsonlines files in {output_dir}")
        for file in tqdm.tqdm(os.listdir(output_dir)):
            if not file.endswith(".jsonl"):
                tqdm.tqdm.write(f"Skipping file {file}")
            with jsonlines.open(os.path.join(output_dir, file), "r") as reader:
                old_annotations = list(reader)
            new_annotations = []
            for annotation in old_annotations:
                new_annotations.append(update_shader(annotation, columns=columns))

            # TODO: DRY - don't repeat yourself?
            output_path = os.path.join(output_dir, file)
            with jsonlines.open(output_path, mode="w") as writer:
                for shader in new_annotations:
                    writer.write(shader)
            tqdm.tqdm.write(f"Annotated {file} to {output_path}")

    else:
        print(f"unrecognized mode {args.mode}, please chose either `update` or `redo`")
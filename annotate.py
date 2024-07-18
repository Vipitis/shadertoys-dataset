import jsonlines
import os
import argparse
import tempfile
import subprocess
from collections.abc import Mapping
from typing import List, Tuple

import tree_sitter_glsl as tsglsl
from tqdm.auto import tqdm
from tree_sitter import Language, Parser
from licensedcode.detection import detect_licenses
from zmq import has

from wgpu_shadertoy.api import shader_args_from_json, _download_media_channels
from wgpu_shadertoy.passes import builtin_variables_glsl, fragment_code_glsl
from wgpu_shadertoy import BufferRenderPass, Shadertoy

GLSL_LANGUAGE = Language(tsglsl.language())
PARSER = Parser(GLSL_LANGUAGE)


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
        elif child.type == "function_definition" and not child.has_error:
            start_header = child.start_byte
            if ((comment_line + 1) != child.start_point[0]): # so we can also get multi line comments at the start (but inline comments?)
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

            funcs.append(tuple([start_comment, start_header, end_header, end_docstring, end_function])) #jsonlines turns this into a list again?
            start_comment = start_header = end_header = end_docstring = end_function = None
            comment_line = -2 # so out empty check can work again
    return funcs


def run_shader(shader_or_code):
    """
    Tests a shader by running it in wgpu-shadertoy. Returns one of the following disjunct classes:
    "ok" - shader ran without error
    "incomplete" - not yet fully supported in wgpu-shadertoy
    "error" - wgpu-shadertoy threw and error (is likely still valid on the website)
    "timedout" - if after 5 seconds we don't get to error or okay.
    # not implemented: "panic" - worst case scenario. a rust panic in wgpu. This can cause the python process to terminate without recovery.
    """
    # return "untested" #placeholder to avoid empty columns for later analysis
    if isinstance(shader_or_code, str):
        # case 1 we only get the only a string of code
        shader_args = {"shader_code": shader_or_code}

    elif isinstance(shader_or_code, Mapping):
        # case 2 we get a dict, always unpack this "Shader" level
        if "Shader" in shader_or_code:
            shader_data = shader_or_code["Shader"]
        else:
            shader_data = shader_or_code
        # case 2.a if we get a default "raw" return?
        if "renderpass" in shader_data:
            shader_args = shader_args_from_json(shader_data)
        # case 2.b we get a flattened json
        elif "image_code" in shader_data: #really lazy check.
            
            buffers = {}
            for buf in "abcd":
                if shader_data[f"buffer_{buf}_code"]:
                    buffers[buf] = BufferRenderPass(buf, code=shader_data[f"buffer_{buf}_code"], inputs=_download_media_channels(shader_data[f"buffer_{buf}_inputs"])[0])
                else:
                    # because we don't handle empty code for Buffers internally.
                    buffers[buf] = ""

            shader_args = {
                "shader_code": shader_data["image_code"],
                "inputs": _download_media_channels(shader_data["image_inputs"])[0],
                "common": shader_data["common_code"],
                "buffers": buffers,
            }
        
    shader_args["shader_type"] = "glsl"
    valid = validate_shader(shader_args["shader_code"]) # this overreports errors due to channels.
    # return valid # don't run Shadertoy just yet...
    if valid != "valid":
        return valid
    
    sub_run = run_shader_in_subprocess(shader_args["shader_code"])

    if sub_run == "ok":
        try:
            shader = Shadertoy(**shader_args, offscreen=True)
            if not shader.complete:
                return "incomplete"
            else:
                return "ok"
        except Exception as e:
            return "error" # other errors have a .message like wgpu ones.
    
    return sub_run

# this is minimal code to try a single pass shader in a subprocess (no inputs)
file_template = """
from wgpu_shadertoy import Shadertoy

shader_code = '''{}'''

shader = Shadertoy(shader_code, shader_type="glsl", offscreen=True)

if __name__ == "__main__":
    shader.show()
    shader.snapshot(0.0)
"""

def run_shader_in_subprocess(shader_code, timeout=5):
    status = "ok" # default case
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(file_template.format(shader_code))
        f.flush()
        try:
            p = subprocess.run(["python", f.name], capture_output=True, timeout=timeout)
            
        except subprocess.SubprocessError as e:
            if isinstance(e, subprocess.TimeoutExpired):
                status = "timeout"
            else:
                status = "error"
            return status

        if p.stderr != b"":
            status = "error"
    
    # cleanup temp file, delete_on_close was only added in Python 3.12?
    os.remove(f.name)

    return status


def validate_shader(image_code: str, seconds: int=5) -> str: 
    """
    this function checks if a renderpass code is valid GLSL with naga.
    it's run in subprocess to catch timeouts after 5 seconds.
    NOTICE: this does not include compatibility code for channel inputs. these will overrepot as errors.
    """
    fragment_code = builtin_variables_glsl + image_code + fragment_code_glsl
    with tempfile.NamedTemporaryFile(mode="w", suffix=".frag", encoding="utf-8") as f, \
        tempfile.NamedTemporaryFile(suffix=".spv", mode="w+b") as f2, \
        tempfile.NamedTemporaryFile(suffix=".wgsl", mode="w+b") as f3: 
        f.write(fragment_code)
        f.flush()
        f2.flush()
        f3.flush()
        try:
            subprocess.run(["naga", f.name], check=True, capture_output=True, timeout=seconds)
            # these additional translations help to catch some panics that run through the validation in naga (maybe fixed in 0.20...)
            subprocess.run(["naga", f.name, f2.name], check=True, capture_output=True, timeout=seconds)
            subprocess.run(["naga", f.name, f3.name], check=True, capture_output=True, timeout=seconds)
            return "valid"
        except subprocess.SubprocessError as e:
            if isinstance(e, subprocess.TimeoutExpired):
                return "timedout"
            # return e.stderr.decode("utf-8")
            #TODO: add a class for panic
            return "error"
        return "valid" #redundant return statement

# gloablly map all columns to the function that calculate them. might need to REGISTER more?
COLUMN_MAP = {"license": check_license, "functions": parse_functions, "test": run_shader}

if __name__ == "__main__":
    args = argument_parser.parse_args()
    print(f"{args=}")
    input_dir = args.input
    output_dir = args.output
    columns = [col.strip() for col in args.columns.split(",")] #if col in list(COLUMN_MAP.values()) + ["all"]]
    print(f"{columns=}")


    if args.mode == "redo":
        print(f"annotating all .jsonlines files in {input_dir}")
        for file in tqdm(os.listdir(input_dir)):
            if not file.endswith(".jsonl"):
                tqdm.write(f"Skipping file {file}")
                continue
            source = "api" #default?
            if file.startswith("20k"): #should we do api_ prefix for the others?
                source = "shaders20k"
            tqdm.write(f"Annotating {file}")
            with jsonlines.open(os.path.join(input_dir, file), "r") as reader:
                shaders = list(reader)
            annotated_shaders = []
            for shader in tqdm(shaders):
                annotated_shaders.append(annotate_shader(shader, columns=columns, access=source))
            
            output_path = os.path.join(output_dir, file)
            with jsonlines.open(output_path, mode="w") as writer:
                for shader in annotated_shaders:
                    writer.write(shader)
            tqdm.write(f"Annotated {file} to {output_path}")

    elif args.mode == "update":
        print(f"updating all .jsonlines files in {output_dir}")
        for file in tqdm(os.listdir(output_dir)):
            if not file.endswith(".jsonl"):
                tqdm.write(f"Skipping file {file}")
                continue
            with jsonlines.open(os.path.join(output_dir, file), "r") as reader:
                old_annotations = list(reader)
            new_annotations = []
            for annotation in tqdm(old_annotations):
                new_annotations.append(update_shader(annotation, columns=columns))

            # TODO: DRY - don't repeat yourself?
            output_path = os.path.join(output_dir, file)
            with jsonlines.open(output_path, mode="w") as writer:
                for shader in new_annotations:
                    writer.write(shader)
            tqdm.write(f"Annotated {file} to {output_path}")

    else:
        print(f"unrecognized mode {args.mode}, please chose either `update` or `redo`")
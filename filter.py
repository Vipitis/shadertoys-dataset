import datasets
import jsonlines
import json
import os
import glob
import pandas as pd
import requests
import argparse
from tqdm.auto import tqdm

# local imports
from annotate import run_shader

# some init?
tqdm.pandas()

argument_parser = argparse.ArgumentParser()
argument_parser.add_argument("--input", type=str, default="./data/annotated/", help="Directory of annotated .jsonlines files. Also looks one subdirectory deeper. Defaults to ./data/annotated/")
argument_parser.add_argument("--output", type=str, default="./data/prepared/", help="Directory to save the prepared dataset to. Defaults to ./data/prepared/")
argument_parser.add_argument("--filters", type=str, default="all", help="Which filters to apply. Defaults to 'all'.") #TODO: negative or positive list?



def load_data(data_dir: os.PathLike) -> pd.DataFrame:
    lines = []
    top_files = glob.glob(data_dir + "*.jsonl")
    sub_files = glob.glob(data_dir + "*/*.jsonl")
    for file in top_files + sub_files:
        with jsonlines.open(file) as reader:
            for obj in reader:
                lines.append(obj)

    out_df = pd.DataFrame(lines)
    out_df["date"] = pd.to_datetime(out_df["date"].astype(int), unit="s")
    return out_df


def filter_public_api(dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    only keep shaders that are published to the API.
    """
    # TODO: Publish API shouldn't be in raw or annotated, this needs to be fixed in both datahalves.
    return dataframe[dataframe["published"].isin(["Public API", 3])]


def filter_licenses(dataframe: pd.DataFrame, keep_base=False, **kwargs) -> pd.DataFrame:
    """
    only keep permissive licenses.
    """
    permissive_list = requests.get("https://huggingface.co/datasets/bigcode-data/license_list/resolve/main/permissive_licenses.txt").content.decode("utf-8").split()
    permissive_list = [license_key.lower() for license_key in permissive_list]
    #TODO: figure out cases with AND and OR in the detection.
    if keep_base:
        permissive_list.append("CC-BY-NC-SA-3.0")
    return dataframe[dataframe["license"].isin(permissive_list)]


def filter_single_pass(dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    only keep shaders that are single pass.
    """
    other_passes = [col for col in dataframe.columns if col.endswith("_code") and col not in ("image_code")]
    #TODO: consider keeping sound_code and common_code (the later one needs to be prepended to the image_code)
    return dataframe[(dataframe.loc[:,other_passes] == "").all(axis=1)]


def filter_no_inputs(dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    only keep shaders that don't require inputs.
    to be used after you filtered for single pass shaders.
    """
    # TODO: consider keeping some channel_types
    return dataframe[dataframe["image_inputs"].apply(len) == 0]

#TODO: inspect if this is the case
def filter_words(dataframe: pd.DataFrame, words=["test", "bug"], **kwargs) -> pd.DataFrame:
    """
    Drop all shaders that contain works like "test", "debug", "ai", "chatGPT", in the title, description or tags.
    """
    for word in words:
        dataframe = dataframe[~dataframe["name"].str.contains(word, case=False)]
        dataframe = dataframe[~dataframe["description"].str.contains(word, case=False)]
        # dataframe = dataframe[~dataframe["tags"]" ".join().str.contains(word, case=False)] # can't do string opeerations on list of tags.

    return dataframe


def filter_working(dataframe: pd.DataFrame, untested=False, **kwargs) -> pd.DataFrame:
    """
    only keep shaders that are working.
    Note: the idea of using `untested=True` is to first run all filters and just get a list of IDs, to then test these.
    Testing is slow and should therefore be only annotated where it's needed.
    """

    # TODO: testing needs to really work before we can rely on this
    drop_values = ["error", "panic", "timeout", "timedout", "valid", "untested"]
    keep_values = ["ok"]
    if untested:
        drop_values.remove("untested")
        keep_values.append("untested")
    return dataframe[dataframe["test"].isin(keep_values)]

PROGRAM_FILTERS = [filter_public_api, filter_licenses, filter_single_pass, filter_no_inputs, filter_words, filter_working]

def filter_programs(dataframe: pd.DataFrame, filters=PROGRAM_FILTERS, **kwargs) -> pd.DataFrame:
    """
    apply a series of filters and print the resulting numbers
    kwargs are passed to the filters
    untested: keep untested shaders (default: False)
    keep_base: keep the base license (default: False)
    """
    print(len(dataframe))

    for f in filters:
        dataframe = f(dataframe, **kwargs)
        print(f"{len(dataframe)} shaderprograms remaining after {f.__name__}")
    return dataframe


def combine_datasets(base_data, add_data):
    """
    combine two datasets, keeping the base data.
    """
    ids_base = set(base_data["id"])
    return pd.concat([base_data, add_data[~add_data["id"].isin(ids_base)]])



# -------------------------
# FUNCTION FILTERS
# -------------------------
def expand_functions(dataframe: pd.DataFrame) -> pd.DataFrame:
    # TODO: likely redundant, since we keep everything... might need some cleanup instead
    cols_to_keep = ["id", "date", "image_code", "functions", "func_bytes", "author", "license"]
    #function byte indicies: start_comment, start_header, end_header, end_docstring, end_function
    func_parts = ["comment", "header", "docstring", "body"]

    # TODO: do we need the whole functions for anything downstream?
    dataframe["functions_"] = dataframe["functions"] # make a copy to keep it past explode
    func_df = dataframe.explode("functions")
    func_df.rename(columns={"functions": "func_bytes", "functions_": "functions"}, inplace=True)
    func_df.dropna(subset=["func_bytes"], inplace=True) # some shaders got not functions parsed ? -> TODO: check the tree-sitter.has_error() result?
    func_df.reset_index(inplace=True)
    for row_idx, row in func_df.iterrows():
        # print(row_idx, row)
        # break
        code = row["image_code"]
        code_bytes = bytes(code, encoding="utf-8")
        # func_bytes = row["func_bytes"]
        for idx, part in enumerate(func_parts):
            start = row["func_bytes"][idx]
            end = row["func_bytes"][idx+1]
            func_df.at[row_idx, part] = code_bytes[start:end].decode(encoding="utf-8")
        
    func_df.drop(columns=func_df.columns.difference(cols_to_keep + func_parts), inplace=True)
    # func_df["date"] = pd.to_datetime(func_df["date"].astype(int), unit="s")

    return func_df

def filter_has_context(dataframe: pd.DataFrame, context="comment", **kwargs) -> pd.DataFrame:
    """
    only keep functions that have a specific context. (not exclusive)
    context: one of "comment", "docstring", "both", "none"
    """
    # TODO: not all are implemented
    if context == "comment":
        return dataframe[dataframe["comment"] != ""]
    elif context == "docstring":
        return dataframe[dataframe["docstring"] != ""]
    elif context == "both":
        return dataframe[(dataframe["comment"] != "") & (dataframe["docstring"] != "")]
    elif context == "none":
        raise NotImplementedError(f"not implemented yet for context: {context}")
    else:
        raise ValueError(f"unknown context: {context}")

# TODO: combine construct_inp and filter_has_context into one function maybe?
def construct_inp(dataframe: pd.DataFrame, context="comment", **kwargs) -> pd.DataFrame:
    """
    adds the model_inp column based on the context.
    """
    if context == "comment":
        dataframe["model_inp"] = dataframe["comment"] + dataframe["header"]
    elif context == "docstring":
        dataframe["model_inp"] = dataframe["header"] + dataframe["docstring"]
    elif context == "both":
        dataframe["model_inp"] = dataframe["comment"] + dataframe["header"] + dataframe["docstring"]
    elif context == "none":
        dataframe["model_inp"] = dataframe["header"]
    else:
        raise ValueError(f"unknown context: {context}")
    return dataframe

def filter_length(dataframe: pd.DataFrame, max_length=2500, **kwargs) -> pd.DataFrame:
    """
    sort out function bodies that are really long. (likely machine generated)
    """
    # TODO: why chose this number?
    return dataframe[dataframe["body"].apply(len) <= max_length]

def filter_alphabetic(dataframe: pd.DataFrame, column="comment", cutoff=0.25, **kwargs) -> pd.DataFrame:
    """
    sort out functions that have an alphabetic ration above the cutoff.
    """
    return dataframe[dataframe[column].apply(lambda x: sum(c.isalpha() for c in x) / len(x)) > cutoff]

def filter_duplicates(dataframe: pd.DataFrame, sort_by="date", **kwargs) -> pd.DataFrame:
    """
    only keeps unique model_inp values. 
    sort_by specifies a column to sort by and keep the top value of. (default is "date")
    the sorting is not kept
    """
    if sort_by not in dataframe.columns:
        raise ValueError(f"unknown column to sort by: {sort_by}")
    # asceding=True and keep="first" are the defualts, meaning we keep ealier entries! 
    # if sorting my views or likes it might might sense to either set ascending=False or keep="last" (not both).
    dataframe.sort_values(by=sort_by, inplace=True, ascending=True)
    out_df = dataframe.drop_duplicates("model_inp", keep="first") #default is "keep first"
    # undo the sort
    return out_df.sort_index()

def filter_needed(dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    only keep functions that are needed. By running the shader with the function removed and seeing if it errors...
    """
    def row_needed(row):
        # print(row["id"])
        code_bytes = bytes(row["image_code"], encoding="utf-8")
        start_comment, start_header, end_header, end_docstring, end_function = row["func_bytes"]
        outer_bytes = code_bytes[:start_comment] + b"\n" +  code_bytes[end_function:]
        test_code = outer_bytes.decode(encoding="utf-8")
        status = run_shader(test_code)
        return status != "ok"
    dataframe["needed"] = dataframe.progress_apply(row_needed, axis=1)
    return dataframe[dataframe["needed"]]

# should this be extracted to main?
FUNCTION_FILTERS = [filter_has_context, construct_inp, filter_length, filter_alphabetic, filter_duplicates, filter_needed]
def filter_functions(dataframe: pd.DataFrame, filters=FUNCTION_FILTERS, **kwargs) -> pd.DataFrame:
    """
    apply a series of filters and print the resulting numbers
    kwargs are passed to the filters
    """
    print(len(dataframe))

    for f in filters:
        dataframe = f(dataframe, **kwargs)
        print(f"{len(dataframe)} functions remaining after {f.__name__}")
    return dataframe


# -------------------------
# DATASET PREPARATION
# -------------------------

def prepare_repo_folder(ds: datasets.Dataset, output_dir: os.PathLike) -> None:
    """
    prepare the dataset to be saved to a folder.
    """

    ds.save_to_disk(output_dir) #this writes the arrow file? I am not sure this is what we want.

    # TODO: write a README.md as dataset card with deps and settings.
    dataset_card = f"""
    # Shadereval dataset created on {pd.Timestamp.now()}
    """
    with open(os.path.join(output_dir, "README.md"), "w") as f:
        f.write(dataset_card)



if __name__ == "__main__":
    args = argument_parser.parse_args()

    if args.filters != "all":
        raise NotImplementedError("only 'all' filters are implemented yet.")

    loaded_data = load_data(args.input)
    # TODO combine.. how?
    print(f"loaded {len(loaded_data)} annotated shader programs")

    filtered_programs = filter_programs(loaded_data)
    print(f"filtered down to {len(filtered_programs)} shader programs")

    all_funcs = expand_functions(loaded_data)
    func_df = expand_functions(filtered_programs)
    print(f"expanded to {len(func_df)} functions")

    filtered_funcs = filter_functions(func_df)
    print(f"filtered down to {len(filtered_funcs)} functions")


    # add extra columns?
    # TODO: this is missing the "docstring" part.
    all_funcs["function"] = all_funcs["header"] + all_funcs["body"]
    filtered_funcs["function"] = filtered_funcs["header"] + filtered_funcs["body"]
    filtered_funcs["function_frequency"] = all_funcs["function"].value_counts()[filtered_funcs["function"]].values
    filtered_funcs["header_frequency"] = all_funcs["header"].value_counts()[filtered_funcs["header"]].values
    clean_func_df = filtered_funcs.drop(columns=["function", "docstring", "needed"])
    # prepare the Dataset?
    initial_df = datasets.Dataset.from_pandas(clean_func_df, split="test")
    clean_df = initial_df.remove_columns(['__index_level_0__'])
    print(clean_df)
    print(f"datas set with {len(clean_df)} functions, and columns: {clean_df.column_names}")
    prepare_repo_folder(clean_df, args.output)